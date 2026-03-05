from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from .models import (
    Client,
    Exchange,
    ClientExchangeAccount,
    PendingPaymentTransaction,
    Settlement,
    Transaction,
    EmailOTP,
    MobileLog,
)


class ClientExchangeAccountInline(admin.TabularInline):
    model = ClientExchangeAccount
    extra = 0
    show_change_link = True
    fields = (
        "exchange",
        "funding",
        "exchange_balance",
        "pending_balance",
        "my_percentage",
        "company_percentage",
        "my_own_percentage",
        "loss_share_percentage",
        "profit_share_percentage",
        "total_share_amount",
        "company_share_amount",
        "updated_at",
    )
    readonly_fields = ("updated_at",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "user", "pending_balance", "is_company_client", "updated_at")
    list_filter = ("is_company_client",)
    search_fields = ("name", "code")
    # CustomUser admin may not be registered; keep this simple.
    inlines = (ClientExchangeAccountInline,)


@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "version_name", "updated_at")
    search_fields = ("name", "code", "version_name")


@admin.register(ClientExchangeAccount)
class ClientExchangeAccountAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "exchange",
        "funding",
        "exchange_balance",
        "computed_pnl_colored",
        "my_percentage",
        "company_percentage",
        "my_own_percentage",
        "total_share_amount",
        "company_share_amount",
        "updated_at",
    )
    list_select_related = ("client", "exchange")
    search_fields = ("client__name", "client__code", "exchange__name", "exchange__code")
    list_filter = ("exchange",)
    autocomplete_fields = ("client", "exchange")
    readonly_fields = ("computed_pnl_colored",)

    def computed_pnl_colored(self, obj: ClientExchangeAccount):
        pnl = obj.compute_client_pnl()
        if pnl == 0:
            return "0"
        color = "#16a34a" if pnl > 0 else "#dc2626"
        return format_html('<span style="color: {}; font-weight: 700;">{}</span>', color, f"{pnl:,}")

    computed_pnl_colored.short_description = "Client PnL"


@admin.register(PendingPaymentTransaction)
class PendingPaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "client", "client_exchange", "type", "amount", "created_by")
    list_select_related = ("client", "client_exchange", "created_by")
    search_fields = ("client__name", "client__code", "notes", "client_exchange__exchange__name")
    list_filter = ("type",)
    autocomplete_fields = ("client", "client_exchange")


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "client_exchange", "amount", "notes")
    list_select_related = ("client_exchange",)
    search_fields = ("client_exchange__client__name", "client_exchange__exchange__name", "notes")
    autocomplete_fields = ("client_exchange",)
    date_hierarchy = "date"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "client_exchange", "type", "amount")
    list_select_related = ("client_exchange",)
    list_filter = ("type",)
    search_fields = ("notes", "client_exchange__client__name", "client_exchange__exchange__name")
    autocomplete_fields = ("client_exchange",)
    date_hierarchy = "date"


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "username", "otp_code", "is_verified", "expires_at", "created_at")
    search_fields = ("email", "username")
    list_filter = ("is_verified",)


@admin.register(MobileLog)
class MobileLogAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "level", "tag", "user")
    search_fields = ("tag", "message", "user__username")
    list_filter = ("level", "tag")
    # CustomUser admin may not be registered; keep this simple.
