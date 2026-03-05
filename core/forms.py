"""
Forms for the Profit-Loss-Share-Settlement System
"""
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from decimal import Decimal
from .models import Client, Exchange, ClientExchangeAccount, Transaction, EmailOTP

User = get_user_model()


class ClientForm(forms.ModelForm):
    """Form for creating/editing clients"""
    class Meta:
        model = Client
        fields = ['name', 'code', 'referred_by', 'is_company_client']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'field-input'}),
            'code': forms.TextInput(attrs={'class': 'field-input'}),
            'referred_by': forms.TextInput(attrs={'class': 'field-input'}),
            'is_company_client': forms.CheckboxInput(attrs={'style': 'width: 18px; height: 18px;'}),
        }


class ExchangeForm(forms.ModelForm):
    """Form for creating/editing exchanges"""
    class Meta:
        model = Exchange
        fields = ['name', 'version_name', 'code']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'field-input'}),
            'version_name': forms.TextInput(attrs={'class': 'field-input'}),
            'code': forms.TextInput(attrs={'class': 'field-input'}),
        }


class ClientExchangeLinkForm(forms.ModelForm):
    """
    Form for linking client to exchange with percentages.
    This is the CONFIGURATION STEP from the document.
    """
    friend_percentage = forms.DecimalField(
        required=False,
        initial=0,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'field-input', 'step': '0.01'}),
        help_text="Friend/Student percentage (report only, decimals allowed)"
    )
    my_own_percentage = forms.DecimalField(
        required=False,
        initial=0,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'field-input', 'step': '0.01'}),
        help_text="Your own percentage (report only, decimals allowed)"
    )
    
    class Meta:
        model = ClientExchangeAccount
        fields = ['client', 'exchange', 'my_percentage']
        widgets = {
            'client': forms.Select(attrs={'class': 'field-input'}),
            'exchange': forms.Select(attrs={'class': 'field-input'}),
            'my_percentage': forms.NumberInput(attrs={'class': 'field-input', 'step': '0.01'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        my_percentage = cleaned_data.get('my_percentage', 0)
        friend_percentage = cleaned_data.get('friend_percentage', 0) or Decimal('0')
        my_own_percentage = cleaned_data.get('my_own_percentage', 0) or Decimal('0')
        
        # Convert to Decimal for precise comparison and ensure they're stored as Decimal
        if isinstance(my_percentage, (int, float)):
            my_percentage = Decimal(str(my_percentage))
        elif not isinstance(my_percentage, Decimal):
            my_percentage = Decimal(str(my_percentage))
        cleaned_data['my_percentage'] = my_percentage
        
        if isinstance(friend_percentage, (int, float)):
            friend_percentage = Decimal(str(friend_percentage))
        elif not isinstance(friend_percentage, Decimal):
            friend_percentage = Decimal(str(friend_percentage))
        cleaned_data['friend_percentage'] = friend_percentage
        
        if isinstance(my_own_percentage, (int, float)):
            my_own_percentage = Decimal(str(my_own_percentage))
        elif not isinstance(my_own_percentage, Decimal):
            my_own_percentage = Decimal(str(my_own_percentage))
        cleaned_data['my_own_percentage'] = my_own_percentage
        
        # Validation Rule: Friend % + My Own % = My Total % (with epsilon for floating point comparison)
        epsilon = Decimal('0.01')
        sum_percentages = friend_percentage + my_own_percentage
        if abs(sum_percentages - my_percentage) >= epsilon:
            raise ValidationError(
                f"Company % ({friend_percentage}) + My Own % ({my_own_percentage}) = {sum_percentages}, "
                f"but My Total % = {my_percentage}. They must be equal."
            )
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Store split percentages directly on the account (single-table storage)
        friend_pct = self.cleaned_data.get("friend_percentage") or Decimal("0")
        my_own_pct = self.cleaned_data.get("my_own_percentage") or Decimal("0")
        instance.company_percentage = friend_pct
        instance.my_own_percentage = my_own_pct

        if commit:
            instance.save()
        
        return instance


class FundingForm(forms.Form):
    """
    Form for adding funding to client exchange account.
    Follows FUNDING RULE: funding += X, exchange_balance += X
    """
    amount = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'field-input', 'placeholder': 'Amount in smallest currency unit'}),
        help_text="Amount to add to funding and exchange balance"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'field-input', 'rows': 3}),
        help_text="Optional notes for this funding transaction"
    )


class ExchangeBalanceUpdateForm(forms.Form):
    """
    Form for updating exchange balance (for trades, fees, etc.)
    Only exchange_balance changes, funding remains untouched.
    """
    new_balance = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'field-input'}),
        help_text="New exchange balance after trade/fee"
    )
    transaction_type = forms.ChoiceField(
        choices=Transaction.TRANSACTION_TYPES[1:],  # Exclude FUNDING
        widget=forms.Select(attrs={'class': 'field-input'}),
        initial='TRADE'
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'field-input', 'rows': 3}),
        help_text="Optional notes for this transaction"
    )


class RecordPaymentForm(forms.Form):
    """
    Form for recording payment (PIN-TO-PIN master document).
    
    Rules:
    - If Client_PnL < 0 (LOSS): funding = funding - paid_amount
    - If Client_PnL > 0 (PROFIT): exchange_balance = exchange_balance - paid_amount
    - paid_amount must be > 0 and <= ABS(Client_PnL)
    """
    paid_amount = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'field-input', 'placeholder': 'Amount in smallest currency unit'}),
        help_text="Amount paid (must be <= ABS(Client_PnL))"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'field-input', 'rows': 3}),
        help_text="Optional notes for this payment"
    )
    
    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account', None)
        super().__init__(*args, **kwargs)
        if self.account:
            max_amount = abs(self.account.compute_client_pnl())
            self.fields['paid_amount'].widget.attrs['max'] = max_amount
            self.fields['paid_amount'].help_text = f"Amount paid (max: {max_amount:,})"
    
    def clean_paid_amount(self):
        paid_amount = self.cleaned_data.get('paid_amount')
        if self.account:
            client_pnl = self.account.compute_client_pnl()
            max_amount = abs(client_pnl)
            
            if paid_amount > max_amount:
                raise ValidationError(
                    f"Paid amount ({paid_amount:,}) cannot exceed ABS(Client_PnL) ({max_amount:,})"
                )
            
            if client_pnl == 0:
                raise ValidationError(
                    "Cannot record payment when Client_PnL = 0 (account is already settled)"
                )
        
        return paid_amount


class SignupForm(forms.Form):
    """Form for user registration with username, email, and password."""
    username = forms.CharField(
        min_length=4,
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'field-input',
            'placeholder': 'Enter your username',
            'autofocus': True,
            'minlength': '4',
            'maxlength': '30'
        }),
        help_text="Required. 4-30 characters. You can use any characters."
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'field-input',
            'placeholder': 'Enter your email address'
        }),
        help_text="Required. We'll send a verification code to this email."
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'field-input',
            'placeholder': 'Enter your password'
        }),
        help_text="Required. Minimum 12 characters.",
        min_length=12
    )
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        
        # Validate length
        if len(username) < 4:
            raise ValidationError("Username must be at least 4 characters long.")
        if len(username) > 30:
            raise ValidationError("Username must be at most 30 characters long.")
        
        # Check for duplicate
        if User.objects.filter(username=username).exists():
            raise ValidationError("A user with this username already exists.")
        
        return username
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email


class OTPVerificationForm(forms.Form):
    """Form for verifying OTP code."""
    otp_code = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'field-input',
            'placeholder': 'Enter 6-digit OTP',
            'autofocus': True,
            'maxlength': '6',
            'pattern': '[0-9]{6}'
        }),
        help_text="Enter the 6-digit code sent to your email."
    )
    
    def __init__(self, *args, **kwargs):
        self.email = kwargs.pop('email', None)
        super().__init__(*args, **kwargs)
    
    def clean_otp_code(self):
        otp_code = self.cleaned_data.get('otp_code')
        if not otp_code.isdigit():
            raise ValidationError("OTP code must contain only digits.")
        return otp_code

