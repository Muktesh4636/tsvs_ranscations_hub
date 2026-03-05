"""
Database models for Profit-Loss-Share-Settlement System
Following PIN-TO-PIN master document specifications.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal


class CustomUser(AbstractUser):
    """
    Custom User model that allows any characters in username.
    Username length: 4-30 characters (no character restrictions).
    """
    # Override username field to remove character restrictions
    username = models.CharField(
        max_length=30,
        unique=True,
        help_text='Required. 4-30 characters. You can use any characters.',
        error_messages={
            'unique': "A user with that username already exists.",
        },
        validators=[],  # Remove default validators that restrict characters
    )
    
    class Meta:
        db_table = 'auth_user'
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return self.username
    
    def clean(self):
        """Custom validation for username length."""
        from django.core.exceptions import ValidationError
        # Don't call super().clean() as it will apply AbstractUser's validators
        if len(self.username) < 4:
            raise ValidationError({'username': 'Username must be at least 4 characters long.'})
        if len(self.username) > 30:
            raise ValidationError({'username': 'Username must be at most 30 characters long.'})


class TimeStampedModel(models.Model):
    """Abstract base to track created/updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Client(TimeStampedModel):
    """
    Client entity - trades on exchange, receives FULL profit, pays FULL loss.
    
    Rules:
    - Client code must be UNIQUE if provided (non-NULL)
    - Client code can be EMPTY/NULL
    - Multiple clients can have the same name
    - If client code is NULL, the index (ID) will always be different
    - Two clients must NEVER have the same non-NULL client code
    """
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    referred_by = models.CharField(max_length=200, blank=True, null=True)
    is_company_client = models.BooleanField(default=False)
    user = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    pending_balance = models.BigIntegerField(default=0)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """
        Validate client code uniqueness.
        
        Rules:
        - Code must be unique if provided (non-NULL)
        - Empty string codes are converted to None
        - Multiple NULL codes are allowed
        """
        from django.core.exceptions import ValidationError
        
        # CRITICAL: Normalize code - convert empty string to None
        # Empty strings ('') conflict with UNIQUE constraint, but NULL values don't
        if self.code:
            self.code = self.code.strip()
        # Convert empty string to None (handles both '' and whitespace-only strings)
        self.code = self.code if self.code else None
        
        # If code is provided (non-NULL), check for duplicates
        if self.code is not None:
            # Check for existing clients with same code
            existing = Client.objects.filter(code=self.code)
            # Exclude self if updating
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            
            if existing.exists():
                existing_client = existing.first()
                raise ValidationError(
                    f"Client code '{self.code}' is already in use by client '{existing_client.name}'. "
                    f"Please choose a different code or leave it blank."
                )
    
    def save(self, *args, **kwargs):
        """Override save to ensure clean() is called and code is properly handled."""
        # CRITICAL: Normalize code - convert empty string to None
        # Empty strings ('') conflict with UNIQUE constraint, but NULL values don't
        if self.code:
            self.code = self.code.strip()
        # Convert empty string to None (handles both '' and whitespace-only strings)
        self.code = self.code if self.code else None
        
        # Run validation
        self.full_clean()
        super().save(*args, **kwargs)


class Exchange(TimeStampedModel):
    """
    Exchange entity - trading platform.
    """
    name = models.CharField(max_length=200)
    version_name = models.CharField(max_length=100, blank=True, null=True, help_text="Version or variant name of the exchange")
    code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    
    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                name='unique_exchange_name_case_insensitive',
                condition=models.Q(name__isnull=False),
            )
        ]
    
    def clean(self):
        """
        Validate that exchange name is unique (case-insensitive).
        """
        from django.core.exceptions import ValidationError
        
        if self.name:
            # Check for case-insensitive duplicate names
            existing = Exchange.objects.filter(name__iexact=self.name)
            if self.pk:
                # Exclude current instance when updating
                existing = existing.exclude(pk=self.pk)
            
            if existing.exists():
                raise ValidationError(
                    f"'{self.name}' already exists."
                )
    
    def save(self, *args, **kwargs):
        """
        Override save to call clean() and enforce case-insensitive uniqueness.
        """
        self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name

    def get_slug(self):
        """URL-safe slug from code or name (e.g. 'dafa', 'diamond')."""
        from django.utils.text import slugify
        value = (self.code or self.name or "").strip()
        return slugify(value) or str(self.pk)


class ClientExchangeAccount(TimeStampedModel):
    """
    CORE SYSTEM TABLE - LOGIC SAFE
    
    Stores ONLY real money values:
    - funding: Total real money given to client
    - exchange_balance: Current balance on exchange
    
    NOTE (2026-03): We also persist share *amount caches* for reporting
    (total share / company share). These are derived from balances +
    configured percentages, but stored to make reporting fast and stable.
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='exchange_accounts')
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='client_accounts')
    
    # ONLY TWO MONEY VALUES STORED (BIGINT as per spec)
    funding = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])
    exchange_balance = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])

    # Client-payments ledger balance scoped to THIS exchange account.
    # Convention (same as Client.pending_balance):
    # pending_balance = total_given - total_received
    # +ve => client owes me, -ve => I owe client
    pending_balance = models.BigIntegerField(default=0)
    
    # Partner percentage (INT as per spec) - kept for backward compatibility
    my_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Your total percentage share (0-100, decimals allowed) - DEPRECATED: Use loss_share_percentage and profit_share_percentage"
    )

    # Report-split percentages (stored on account for admin visibility).
    # Invariant (soft): company_percentage + my_own_percentage == my_percentage
    company_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Company percentage (part of My Total %)."
    )
    my_own_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="My own percentage (part of My Total %)."
    )
    
    # MASKED SHARE SETTLEMENT SYSTEM: Separate loss and profit percentages
    loss_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Admin share percentage for losses (0-100, decimals allowed). IMMUTABLE once data exists."
    )
    profit_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Admin share percentage for profits (0-100, decimals allowed). Can change anytime, affects only future profits."
    )

    # Persisted share amount caches (derived, but stored for reporting)
    # Values are always >= 0, and represent amounts in the same units as funding/exchange_balance.
    total_share_amount = models.BigIntegerField(
        default=0,
        help_text="Cached total share amount for current balances (>=0)."
    )
    company_share_amount = models.BigIntegerField(
        default=0,
        help_text="Cached company share amount (portion of total_share_amount, >=0)."
    )
    
    # CRITICAL FIX: Lock share at first compute per PnL cycle
    # These fields store the locked values when a PnL cycle starts
    locked_initial_final_share = models.BigIntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Initial FinalShare locked at start of PnL cycle. Used for remaining calculation."
    )
    locked_share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        null=True,
        blank=True,
        help_text="Share percentage locked at start of PnL cycle. Prevents historical rewrite."
    )
    locked_initial_pnl = models.BigIntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Initial PnL when share was locked. Used to detect PnL cycle changes."
    )
    cycle_start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when current PnL cycle started. Used to filter settlements by cycle."
    )
    locked_initial_funding = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Funding amount when share was locked. Used to detect funding changes that should reset cycle."
    )
    
    class Meta:
        ordering = ['client__name', 'exchange__name']
    
    def __str__(self):
        return f"{self.client.name} - {self.exchange.name}"
    
    def compute_client_pnl(self):
        """
        MASTER PROFIT/LOSS FORMULA
        Client_PnL = exchange_balance - funding
        
        Returns: BIGINT (can be negative for loss)
        """
        return self.exchange_balance - self.funding
    
    def get_share_percentage(self, client_pnl=None):
        """
        BASE LOGIC: Get appropriate share percentage based on PnL direction.
        
        Rules:
        - If client_pnl < 0 (LOSS): Use loss_share_percentage if set and > 0, else my_percentage
        - If client_pnl > 0 (PROFIT): Use profit_share_percentage if set and > 0, else my_percentage
        - If client_pnl == 0: Return 0 (no share on zero PnL)
        
        Args:
            client_pnl: Optional PnL value. If None, computes from current balances.
        
        Returns:
            Decimal: Share percentage (0-100)
        """
        if client_pnl is None:
            client_pnl = self.compute_client_pnl()
        
        if client_pnl < 0:
            # LOSS CASE: Use loss_share_percentage if set and > 0, else fallback to my_percentage
            share_pct = self.loss_share_percentage if self.loss_share_percentage and self.loss_share_percentage > 0 else self.my_percentage
        elif client_pnl > 0:
            # PROFIT CASE: Use profit_share_percentage if set and > 0, else fallback to my_percentage
            share_pct = self.profit_share_percentage if self.profit_share_percentage and self.profit_share_percentage > 0 else self.my_percentage
        else:
            # ZERO PnL: No share
            share_pct = Decimal('0')
        
        # Ensure Decimal type for consistency
        if not isinstance(share_pct, Decimal):
            share_pct = Decimal(str(share_pct))
            
        return share_pct
    
    def compute_masked_capital(self, share_payment):
        """
        Calculate masked capital from share payment.
        
        Formula: MaskedCapital = (SharePayment × abs(LockedInitialPnL)) / LockedInitialFinalShare
        
        This ensures SharePayment maps back to PnL linearly, not exponentially.
        
        Args:
            share_payment: Share payment amount (integer)
        
        Returns:
            int: Masked capital amount
        """
        settlement_info = self.get_remaining_settlement_amount()
        initial_final_share = settlement_info['initial_final_share']
        locked_initial_pnl = self.locked_initial_pnl
        
        if initial_final_share == 0 or locked_initial_pnl is None:
            return 0
        
        return int((share_payment * abs(locked_initial_pnl)) / initial_final_share)
    
    def compute_my_share(self):
        """
        MASKED SHARE SETTLEMENT SYSTEM - PARTNER SHARE FORMULA
        
        Uses floor() rounding (round down) for final share.
        Separate percentages for loss and profit.
        
        Returns: BIGINT (always positive, floor rounded)
        """
        import math
        try:
            client_pnl = self.compute_client_pnl()
            
            if client_pnl == 0:
                return 0
            
            # Use helper method to get appropriate share percentage
            share_pct = self.get_share_percentage(client_pnl)

            # Ensure share_pct is a Decimal for precise calculation
            if not isinstance(share_pct, Decimal):
                share_pct = Decimal(str(share_pct))

            # Exact Share (NO rounding)
            exact_share = Decimal(str(abs(client_pnl))) * (share_pct / Decimal('100'))

            # Final Share (ONLY rounding step) - FLOOR (round down)
            final_share = math.floor(float(exact_share))
            
            return int(final_share)
        except Exception as e:
            print(f"Error in compute_my_share for account {self.id}: {e}")
            return 0

    def _compute_share_amount_cache(self):
        """
        Compute (total_share_amount, company_share_amount) for current balances.

        - total_share_amount: admin total share from masked-share system (always >= 0)
        - company_share_amount: portion of total_share_amount based on stored split
          (company_percentage / my_percentage). If company_percentage is 0, company share = 0.
        """
        from decimal import Decimal, ROUND_FLOOR

        total_share = int(self.compute_my_share() or 0)
        if total_share <= 0:
            return 0, 0

        # Default: no company split configured
        my_total_pct = Decimal(str(self.my_percentage or 0))
        friend_pct = Decimal(str(self.company_percentage or 0))

        if my_total_pct <= 0 or friend_pct <= 0:
            return total_share, 0

        # Company share is proportional to friend% within my total%
        ratio = friend_pct / my_total_pct
        if ratio <= 0:
            return total_share, 0
        if ratio >= 1:
            return total_share, total_share

        company_share = int(
            (Decimal(total_share) * ratio).to_integral_value(rounding=ROUND_FLOOR)
        )
        company_share = max(0, min(total_share, company_share))
        return total_share, company_share

    def save(self, *args, **kwargs):
        """
        Keep share caches consistent whenever balances/percentages change.
        """
        try:
            total_share, company_share = self._compute_share_amount_cache()
            self.total_share_amount = int(total_share)
            self.company_share_amount = int(company_share)
        except Exception:
            # Never block saving core money values because cache failed
            pass

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            # Ensure caches persist even when caller uses update_fields
            uf = set(update_fields)
            uf.update({"total_share_amount", "company_share_amount"})
            kwargs["update_fields"] = list(uf)

        super().save(*args, **kwargs)
    
    def compute_exact_share(self):
        """
        MASKED SHARE SETTLEMENT SYSTEM - Exact Share (before rounding)
        
        Returns: float (exact share before floor rounding)
        """
        try:
            client_pnl = self.compute_client_pnl()
            
            if client_pnl == 0:
                return 0.0
            
            # Use helper method to get appropriate share percentage
            share_pct = self.get_share_percentage(client_pnl)

            # Ensure share_pct is a Decimal for precise calculation
            if not isinstance(share_pct, Decimal):
                share_pct = Decimal(str(share_pct))

            # Exact Share (NO rounding)
            exact_share = Decimal(str(abs(client_pnl))) * (share_pct / Decimal('100'))

            return float(exact_share)
        except Exception as e:
            print(f"Error in compute_exact_share for account {self.id}: {e}")
            return 0.0
    
    def lock_initial_share_if_needed(self):
        """
        CRITICAL FIX: Lock InitialFinalShare at first compute per PnL cycle.
        
        This ensures share doesn't shrink after payments.
        Share is decided by trading outcome, not by settlement.
        
        NEW FIX: Funding change should reset cycle (new exposure = new cycle).
        """
        client_pnl = self.compute_client_pnl()
        
        # CRITICAL FIX: PnL magnitude reduction should reset cycle (trading reduced exposure)
        # If PnL magnitude reduced significantly, old lock is invalid
        if self.locked_initial_pnl is not None and client_pnl != 0:
            locked_pnl_abs = abs(self.locked_initial_pnl)
            current_pnl_abs = abs(client_pnl)
            
            # If PnL magnitude reduced, trading has reduced exposure → old lock invalid
            # This prevents stale locked shares from persisting when profit/loss shrinks
            if current_pnl_abs < locked_pnl_abs:
                # PnL magnitude reduced → reset cycle to allow re-lock with new (smaller) PnL
                self.locked_initial_final_share = None
                self.locked_share_percentage = None
                self.locked_initial_pnl = None
                self.cycle_start_date = None
                self.locked_initial_funding = None
                # Save reset before continuing
                self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
        
        # CRITICAL FIX: Funding change should reset cycle (new exposure = new cycle)
        # If funding changed after cycle was locked, reset the cycle
        if self.locked_initial_final_share is not None:
            # Check if funding tracking exists (new data) or is missing (old data)
            if self.locked_initial_funding is not None:
                # New data: Compare with tracked funding
                if self.funding != self.locked_initial_funding:
                    # Funding changed → new exposure → new cycle
                    # Reset all locks to force new cycle
                    self.locked_initial_final_share = None
                    self.locked_share_percentage = None
                    self.locked_initial_pnl = None
                    self.cycle_start_date = None
                    self.locked_initial_funding = None
                    # Save reset before continuing
                    self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
            else:
                # Old data: locked_initial_funding is None (from before this fix)
                # For old data without funding tracking, we can't reliably detect funding changes
                # The PnL magnitude reduction check above will handle trading reductions
                # For funding increases, we'll set locked_initial_funding to current funding
                # so future checks can detect funding changes
                if self.locked_initial_funding is None:
                    # Set it now for future checks (migration from old data)
                    self.locked_initial_funding = self.funding
                    self.save(update_fields=['locked_initial_funding'])
        
        # If no locked share exists, or PnL cycle changed (sign flip or zero crossing), lock new share
        if self.locked_initial_final_share is None or self.locked_initial_pnl is None:
            # First time - lock the share
            final_share = self.compute_my_share()
            if final_share > 0:
                # Use helper method to get appropriate share percentage
                share_pct = self.get_share_percentage(client_pnl)
                
                self.locked_initial_final_share = final_share
                self.locked_share_percentage = share_pct
                self.locked_initial_pnl = client_pnl
                self.cycle_start_date = timezone.now()  # Track when this cycle started
                self.locked_initial_funding = self.funding  # Track funding when cycle started
                self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
        elif client_pnl != 0 and self.locked_initial_pnl != 0:
            # Check if PnL cycle changed (sign flip)
            if (client_pnl < 0) != (self.locked_initial_pnl < 0):
                # PnL cycle changed - lock new share
                final_share = self.compute_my_share()
                if final_share > 0:
                    # Use helper method to get appropriate share percentage
                    share_pct = self.get_share_percentage(client_pnl)
                    
                    self.locked_initial_final_share = final_share
                    self.locked_share_percentage = share_pct
                    self.locked_initial_pnl = client_pnl
                    self.cycle_start_date = timezone.now()  # NEW CYCLE: Track when this cycle started
                    self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date'])
        elif client_pnl == 0:
            # PnL is zero - only reset locks if there are no pending settlements
            # CRITICAL FIX: Don't reset locked share if there's still remaining settlement amount
            # CRITICAL FIX: Only count settlements from current cycle
            if self.cycle_start_date:
                cycle_settled = self.settlements.filter(
                    date__gte=self.cycle_start_date
                ).aggregate(
                    total=models.Sum('amount')
                )['total'] or 0
            else:
                cycle_settled = self.settlements.aggregate(
                    total=models.Sum('amount')
                )['total'] or 0
            
            # Only reset if locked share is fully settled (or no locked share exists)
            if self.locked_initial_final_share is None or cycle_settled >= (self.locked_initial_final_share or 0):
                # Fully settled or no share - safe to reset
                self.locked_initial_final_share = None
                self.locked_share_percentage = None
                self.locked_initial_pnl = None
                self.cycle_start_date = None
                self.locked_initial_funding = None
                self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
            # Otherwise, keep the locked share even if PnL is 0 (settlements may have brought it to zero)
    
    def close_cycle(self):
        """
        Close the current PnL cycle by resetting all cycle-related fields.
        
        This method is called when:
        - Manual funding is added (new exposure = new cycle)
        - Auto re-funding occurs after settlement (new cycle starts)
        - Full settlement is completed (cycle ends)
        
        Resets all locked cycle values to allow a new cycle to start.
        """
        self.locked_initial_final_share = None
        self.locked_share_percentage = None
        self.locked_initial_pnl = None
        self.cycle_start_date = None
        self.locked_initial_funding = None
        self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
    
    def get_remaining_settlement_amount(self):
        """
        CRITICAL FIX: Calculate remaining using LOCKED InitialFinalShare.
        
        Formula: RemainingRaw = LockedInitialFinalShare - Sum(SharePayments)
        Overpaid = max(0, Sum(SharePayments) - LockedInitialFinalShare)
        
        Share is locked at first compute and NEVER shrinks after payments.
        This ensures share is decided by trading outcome, not by settlement.
        
        IMPORTANT: This method returns RemainingRaw (always ≥ 0).
        The SIGN must be applied at DISPLAY TIME based on Client_PnL direction:
        
        Display Logic (MUST be applied by caller):
        - IF Client_PnL < 0 (LOSS): DisplayRemaining = +RemainingRaw (client owes you)
        - IF Client_PnL > 0 (PROFIT): DisplayRemaining = -RemainingRaw (you owe client)
        
        Returns: dict with 'remaining' (raw value ≥ 0), 'overpaid', 'initial_final_share', and 'total_settled'
        """
        # Lock share if needed
        self.lock_initial_share_if_needed()
        
        # CRITICAL FIX: Only count settlements from CURRENT cycle
        # When PnL sign changes (LOSS → PROFIT or PROFIT → LOSS), a NEW cycle starts
        # Old cycle settlements must NOT mix with new cycle shares
        if self.cycle_start_date:
            # Only count settlements that occurred AFTER this cycle started
            total_settled = self.settlements.filter(
                date__gte=self.cycle_start_date
            ).aggregate(
                total=models.Sum('amount')
            )['total'] or 0
        else:
            # No cycle start date - count all settlements (backward compatibility)
            total_settled = self.settlements.aggregate(
                total=models.Sum('amount')
            )['total'] or 0
        
        # CRITICAL: Always use locked share - NEVER recalculate from current PnL
        # If locked share doesn't exist, check if we should lock current share
        if self.locked_initial_final_share is not None:
            initial_final_share = self.locked_initial_final_share
        else:
            # No locked share - check if current share > 0 and should be locked
            current_share = self.compute_my_share()
            if current_share > 0:
                # Current share exists but not locked - lock it now
                client_pnl = self.compute_client_pnl()
                # Use helper method to get appropriate share percentage
                share_pct = self.get_share_percentage(client_pnl)
                
                self.locked_initial_final_share = current_share
                self.locked_share_percentage = share_pct
                self.locked_initial_pnl = client_pnl
                self.cycle_start_date = timezone.now()  # Track when this cycle started
                self.locked_initial_funding = self.funding  # Track funding when cycle started
                self.save(update_fields=['locked_initial_final_share', 'locked_share_percentage', 'locked_initial_pnl', 'cycle_start_date', 'locked_initial_funding'])
                initial_final_share = current_share
            else:
                # No locked share and current share is 0 - no settlement possible
                return {
                    'remaining': 0,
                    'overpaid': 0,
                    'initial_final_share': 0,
                    'total_settled': total_settled
                }
        
        # CORRECT FORMULA: Remaining = LockedInitialFinalShare - TotalSettled
        # Share NEVER shrinks - it's locked at initial compute
        remaining = max(0, initial_final_share - total_settled)
        overpaid = max(0, total_settled - initial_final_share)
        
        return {
            'remaining': remaining,
            'overpaid': overpaid,
            'initial_final_share': initial_final_share,
            'total_settled': total_settled
        }
    
    def get_remaining_settlement_amount_legacy(self):
        """
        Legacy method for backward compatibility.
        Returns just the remaining amount (for existing code).
        """
        result = self.get_remaining_settlement_amount()
        return result['remaining']
    
    def clean(self):
        """
        MASKED SHARE SETTLEMENT SYSTEM - Validation
        
        NOTE:
        We do NOT block editing loss/profit share percentages anymore.
        Historical settlement safety is enforced by cycle locking
        (`locked_share_percentage`, `locked_initial_final_share`, etc.), so it’s
        safe to allow edits for future cycles without rewriting past cycles.
        """
        return
    
    def is_settled(self):
        """
        Check if client PnL is zero (trading flat).
        
        Note: This does NOT mean "settlement complete".
        PnL = 0 can occur from:
        - Trading result (no settlements)
        - Settlement activity
        - Over-settlement + clamp
        
        Use get_remaining_settlement_amount() == 0 to check if settlement is complete.
        """
        return self.compute_client_pnl() == 0


class Settlement(TimeStampedModel):
    """
    MASKED SHARE SETTLEMENT SYSTEM - Settlement Tracking
    
    Tracks individual settlement payments to prevent over-settlement.
    Each settlement records a partial or full payment of the admin's share.
    """
    client_exchange = models.ForeignKey(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='settlements'
    )
    amount = models.BigIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Settlement amount (integer, > 0)"
    )
    date = models.DateTimeField(help_text="Date when payment was made")
    notes = models.TextField(blank=True, null=True, help_text="Optional notes about this settlement")
    
    class Meta:
        ordering = ['-date', '-id']
    
    def __str__(self):
        return f"Settlement: {self.client_exchange} - {self.amount} - {self.date.strftime('%Y-%m-%d')}"


class Transaction(TimeStampedModel):
    """
    TRANSACTIONS TABLE - AUDIT ONLY
    
    Stores transaction history for audit purposes.
    NEVER used to recompute balances.
    
    Each transaction represents exactly one financial intent:
    - FUNDING_MANUAL: User adds capital
    - FUNDING_AUTO: Optional re-funding after settlement
    - TRADE: Exchange trading activity
    - SETTLEMENT_SHARE: Share payment (profit/loss)
    
    Balance mutations are stored as before/after values for audit trail.
    """
    TRANSACTION_TYPES = [
        ('FUNDING_MANUAL', 'Funding'),
        ('FUNDING_AUTO', 'Auto Re-Funding'),
        ('TRADE', 'Trade'),
        ('SETTLEMENT_SHARE', 'Settlement Share Payment'),
        ('FEE', 'Fee'),
        ('ADJUSTMENT', 'Adjustment'),
        ('UPDATE_BALANCE', 'Update Balance'),
        # Legacy types for backward compatibility
        ('FUNDING', 'Funding (Legacy)'),
        ('RECORD_PAYMENT', 'Record Payment'),
    ]
    
    client_exchange = models.ForeignKey(
        ClientExchangeAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    date = models.DateTimeField()
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.BigIntegerField(help_text="Amount in smallest currency unit (signed, for reporting only)")
    
    # Balance tracking for audit trail
    funding_before = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Funding before this transaction (for audit)"
    )
    funding_after = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Funding after this transaction (for audit)"
    )
    exchange_balance_before = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Exchange balance before this transaction (for audit)"
    )
    exchange_balance_after = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Exchange balance after this transaction (for audit)"
    )
    
    # Sequence number for ordering (auto-increment per account)
    sequence_no = models.IntegerField(
        default=0,
        help_text="Sequence number for ordering transactions (auto-increment per account)"
    )
    
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['client_exchange', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.type} - {self.client_exchange} - {self.date.strftime('%Y-%m-%d')}"
    
    def save(self, *args, **kwargs):
        """
        Auto-increment sequence_no per account if not provided.
        """
        if not self.sequence_no:
            # Get the max sequence_no for this account
            max_seq = Transaction.objects.filter(
                client_exchange=self.client_exchange
            ).aggregate(
                max_seq=models.Max('sequence_no')
            )['max_seq'] or 0
            self.sequence_no = max_seq + 1
        super().save(*args, **kwargs)


class EmailOTP(TimeStampedModel):
    """
    Model to store OTP codes for email verification during signup.
    """
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150)
    otp_code = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'otp_code']),
        ]
    
    def __str__(self):
        return f"OTP for {self.email} - {'Verified' if self.is_verified else 'Pending'}"
    
    def is_expired(self):
        """Check if OTP has expired."""
        from django.utils import timezone
        return timezone.now() > self.expires_at


class MobileLog(TimeStampedModel):
    """
    Store logs from mobile app (Android APK).
    """
    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]
    
    user = models.ForeignKey('CustomUser', on_delete=models.CASCADE, related_name='mobile_logs', null=True, blank=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='INFO')
    tag = models.CharField(max_length=100, blank=True, help_text='Log tag/category (e.g., "ApiClient", "LoginActivity")')
    message = models.TextField(help_text='Log message')
    device_info = models.CharField(max_length=200, blank=True, help_text='Device model, OS version, etc.')
    app_version = models.CharField(max_length=50, blank=True, help_text='App version name')
    stack_trace = models.TextField(blank=True, help_text='Stack trace for errors')
    extra_data = models.JSONField(default=dict, blank=True, help_text='Additional metadata')
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['level']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"[{self.level}] {self.tag}: {self.message[:50]}"


class PendingPaymentTransaction(TimeStampedModel):
    """
    Tracks money given to and received from clients.
    Formula: BALANCE = TOTAL_GIVEN - TOTAL_RECEIVED
    """
    TYPE_CHOICES = [
        ('GIVEN', 'GIVEN'),
        ('RECEIVED', 'RECEIVED'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='pending_transactions')
    client_exchange = models.ForeignKey(
        ClientExchangeAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
        help_text="Optional link to a specific client-exchange account to keep payments separate per account."
    )
    date = models.DateTimeField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.BigIntegerField(validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='created_pending_transactions')

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.type} - {self.client.name} - {self.amount}"

    def save(self, *args, **kwargs):
        """
        Live Running Balance Logic:
        BALANCE = TOTAL_GIVEN - TOTAL_RECEIVED
        """
        is_new = self.pk is None
        old_amount = 0
        old_type = None
        old_client_exchange = None
        
        if not is_new:
            # Get the original transaction to reverse its effect
            old_instance = PendingPaymentTransaction.objects.get(pk=self.pk)
            old_amount = old_instance.amount
            old_type = old_instance.type
            old_client_exchange = old_instance.client_exchange

        # Use atomic transaction to ensure balance consistency
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            # 1. Reverse old effect if editing
            if not is_new:
                if old_type == 'GIVEN':
                    self.client.pending_balance -= old_amount
                elif old_type == 'RECEIVED':
                    self.client.pending_balance += old_amount

                if old_client_exchange:
                    if old_type == 'GIVEN':
                        old_client_exchange.pending_balance -= old_amount
                    elif old_type == 'RECEIVED':
                        old_client_exchange.pending_balance += old_amount
                    old_client_exchange.save(update_fields=['pending_balance'])
            
            # 2. Apply new effect
            if self.type == 'GIVEN':
                self.client.pending_balance += self.amount
            elif self.type == 'RECEIVED':
                self.client.pending_balance -= self.amount

            if self.client_exchange:
                if self.type == 'GIVEN':
                    self.client_exchange.pending_balance += self.amount
                elif self.type == 'RECEIVED':
                    self.client_exchange.pending_balance -= self.amount
                self.client_exchange.save(update_fields=['pending_balance'])
            
            # 3. Save client and transaction
            self.client.save(update_fields=['pending_balance'])
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Delete Transaction Logic:
        Reverse the effect of the transaction on the client's balance.
        """
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            if self.type == 'GIVEN':
                self.client.pending_balance -= self.amount
            elif self.type == 'RECEIVED':
                self.client.pending_balance += self.amount

            if self.client_exchange:
                if self.type == 'GIVEN':
                    self.client_exchange.pending_balance -= self.amount
                elif self.type == 'RECEIVED':
                    self.client_exchange.pending_balance += self.amount
                self.client_exchange.save(update_fields=['pending_balance'])
            
            self.client.save(update_fields=['pending_balance'])
            super().delete(*args, **kwargs)


