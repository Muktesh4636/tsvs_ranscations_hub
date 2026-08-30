"""
URL configuration for core app
"""
from django.urls import path, include, reverse_lazy
from django.contrib.auth import views as auth_views
from django.http import HttpResponseRedirect
from rest_framework.routers import DefaultRouter
from . import views, api_views
from .forms import ChipPasswordResetForm, ChipSetPasswordForm

# API Router
router = DefaultRouter()
router.register(r'clients', api_views.ClientViewSet, basename='api-client')
router.register(r'exchanges', api_views.ExchangeViewSet, basename='api-exchange')
router.register(r'accounts', api_views.ClientExchangeAccountViewSet, basename='api-account')
router.register(r'transactions', api_views.TransactionViewSet, basename='api-transaction')

def root_redirect(request):
    """Redirect root URL to dashboard"""
    return HttpResponseRedirect('/clients/dashboard/')

urlpatterns = [
    # Root redirect to dashboard
    path('', root_redirect, name='root-redirect'),

    # Health check for monitoring
    path('health/', views.health_check, name='health_check'),

    # API Root (public access) - now at /api/ instead of root
    path('api/', api_views.api_root, name='api-root'),

    # API Routes
    path('api/login/', api_views.api_login, name='api-login'),
    path('api/mobile-dashboard/', api_views.mobile_dashboard_summary, name='api-mobile-dashboard'),
    path('api/pending-payments/', api_views.api_pending_payments, name='api-pending-payments'),
    path('api/pending/export/', api_views.api_export_pending_csv, name='api-pending-export'),
    path('api/accounts/<int:account_id>/funding/', api_views.api_add_funding, name='api-funding'),
    path('api/accounts/<int:account_id>/balance/', api_views.api_update_balance, name='api-balance'),
    path('api/accounts/<int:account_id>/payment/', api_views.api_record_payment, name='api-payment'),
    path('api/accounts/link/', api_views.api_link_exchange, name='api-link-account'),
    path('api/reports-summary/', api_views.api_reports_summary, name='api-reports-summary'),
    path('api/exchanges/create/', api_views.api_create_exchange, name='api-create-exchange'),
    path('api/transactions/<int:pk>/delete/', api_views.api_delete_transaction, name='api-delete-transaction'),
    path('api/transactions/<int:pk>/edit/', api_views.api_edit_transaction, name='api-edit-transaction'),
    path('api/exchanges/<int:pk>/delete/', api_views.api_delete_exchange, name='api-delete-exchange'),
    path('api/accounts/<int:account_id>/settings/', api_views.api_update_account_settings, name='api-account-settings'),
    path('api/accounts/<int:account_id>/report-config/', api_views.api_account_report_config, name='api-account-report-config'),
    path('api/clients/<int:pk>/delete/', api_views.api_delete_client, name='api-client-delete-mobile'),
    path('api/mobile-logs/', api_views.api_submit_mobile_log, name='api-submit-mobile-log'),
    path('api/backups/status/', api_views.api_backup_status, name='api-backup-status'),
    path('api/', include(router.urls)),  # Changed from '' to 'api/' to avoid conflict
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('api/token-auth/', include('rest_framework.urls')), # Simplified for token login later

    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('account/profile/', views.user_profile, name='user_profile'),
    path(
        'account/password-change/',
        views.PasswordChangeWithNotificationView.as_view(),
        name='password_change',
    ),
    path(
        'account/password-change/done/',
        auth_views.PasswordChangeDoneView.as_view(
            template_name='core/auth/password_change_done.html',
        ),
        name='password_change_done',
    ),
    path(
        'account/password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='core/auth/password_reset_form.html',
            email_template_name='core/auth/password_reset_email.txt',
            subject_template_name='core/auth/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'account/password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='core/auth/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'account/reset/<uidb64>/<token>/',
        views.PasswordResetConfirmWithAdminNotifyView.as_view(
            form_class=ChipSetPasswordForm,
            template_name='core/auth/password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'account/reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='core/auth/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path('signup/', views.signup_view, name='signup'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('resend-otp/', views.resend_otp_view, name='resend_otp'),
    
    # Dashboard
    path('clients/dashboard/', views.dashboard, name='dashboard'),
    path('client-payments/dashboard/', views.dashboard, name='payments_dashboard'),
    path('client_payment/dashboard/', views.dashboard),  # Alias for typo
    
    # Clients
    path('clients/list/', views.client_list, name='client_list'),
    path('client-payments/clients/', views.client_list, name='payments_client_list'),
    path('client_payment/clients/', views.client_list),  # Alias for typo
    path('clients/create/', views.client_create, name='client_create'),
    path('clients/detail/<int:pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:pk>/', views.client_detail),  # Alias for old URL
    path('client-payments/clients/detail/<int:pk>/', views.client_detail, name='payments_client_detail'),
    path('client-payments/clients/<int:pk>/', views.client_detail),  # Alias for old URL
    path('client_payment/clients/detail/<int:pk>/', views.client_detail),  # Alias for typo
    path('client_payment/clients/<int:pk>/', views.client_detail),  # Alias for typo
    path('clients/<int:pk>/delete/', views.client_delete, name='client_delete'),
    
    # Exchanges
    path('clients/exchanges/', views.exchange_list, name='exchange_list'),
    path('client-payments/exchanges/', views.exchange_list, name='payments_exchange_list'),
    path('client_payment/exchanges/', views.exchange_list),  # Alias for typo
    path('exchanges/create/', views.exchange_create, name='exchange_create'),
    path('exchanges/link/', views.link_client_to_exchange, name='exchange_link'),
    # Canonical client account URL includes exchange slug (dafa/diamond/etc)
    path('clients/exchanges/account/<int:pk>/<slug:exchange_slug>/', views.exchange_account_detail, name='exchange_account_detail_with_slug'),
    # Back-compat: redirect old URL to slugged URL
    path('clients/exchanges/account/<int:pk>/', views.exchange_account_detail_redirect_with_slug_clients, name='exchange_account_detail'),
    path('client-payments/exchanges/account/<int:pk>/<slug:exchange_slug>/', views.exchange_account_detail, name='payments_exchange_account_detail'),
    path('client-payments/exchanges/account/<int:pk>/<slug:exchange_slug>/settlement/', views.pending_payment_settlement, name='pending_payment_settlement'),
    path('client-payments/exchanges/account/<int:pk>/', views.exchange_account_detail_redirect_with_slug, name='payments_exchange_account_detail_redirect'),
    path('exchanges/account/<int:pk>/', views.exchange_account_detail),  # Alias for backward compatibility
    path('exchanges/account/<int:pk>/edit/', views.client_exchange_edit, name='client_exchange_edit'),
    path('exchanges/account/<int:pk>/delete/', views.client_exchange_delete, name='client_exchange_delete'),
    
    # Funding & Transactions
    path('exchanges/account/<int:account_id>/funding/', views.add_funding, name='add_funding'),
    path('exchanges/account/<int:account_id>/update-balance/', views.update_exchange_balance, name='update_balance'),
    path('exchanges/account/<int:account_id>/record-payment/', views.record_payment, name='record_payment'),
    
    # Transactions (audit trail)
    path('clients/transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),
    path('client-payments/transactions/', views.pending_payment_transactions_list, name='payments_transaction_list'),
    path('client_payment/transactions/', views.pending_payment_transactions_list),  # Alias for typo
    
    # Settlements
    path('clients/settlements/', views.pending_summary, name='pending_summary'),
    path('clients/settlements/settle-all/', views.settle_all_payments, name='settle_all_payments'),
    path('client-payments/settlements/', views.pending_payments_list, name='payments_settlements_list'),
    path('client_payment/settlements/', views.pending_payments_list),  # Alias for typo
    path('pending/export/', views.export_pending_csv, name='export_pending_csv'),
    path('pending/export/<int:client_id>/', views.export_client_pending_csv, name='export_client_pending_csv'),
    
    # Reports
    path('clients/reports/', views.report_overview, name='report_overview'),
    path('client-payments/reports/', views.report_overview, name='payments_report_overview'),
    path('client_payment/reports/', views.report_overview),  # Alias for typo
    path('reports/daily/', views.report_daily, name='report_daily'),
    path('reports/weekly/', views.report_weekly, name='report_weekly'),
    path('reports/monthly/', views.report_monthly, name='report_monthly'),
    path('reports/custom/', views.report_custom, name='report_custom'),
    path('api/reports/custom/', api_views.api_custom_reports, name='api-custom-reports'),
    path('api/reports/export/', api_views.api_export_reports_csv, name='api-export-reports-csv'),
    path('reports/client/<int:pk>/', views.report_client, name='report_client'),
    path('reports/exchange/<int:pk>/', views.report_exchange, name='report_exchange'),
    path('reports/time-travel/', views.report_time_travel, name='report_time_travel'),

    # APK Downloads
    path('build/apk/', views.build_apk, name='build_apk'),
    path('download/apk/', views.download_apk, name='download_apk'),
    
    # Pending Payments (New System)
    path('client-payments/pending-payments/', views.pending_payments_list, name='payments_pending_payments_list'),
    path('client_payment/pending-payments/', views.pending_payments_list),  # Alias for typo
    path('pending-payments/', views.pending_payments_list, name='pending_payments_list'),
    path('pending-payments/transactions/', views.pending_payment_transactions_list, name='pending_payment_transactions_list'),
    path('pending-payments/<int:pk>/edit/', views.pending_payment_edit, name='pending_payment_edit'),
    path('pending-payments/<int:pk>/delete/', views.pending_payment_delete, name='pending_payment_delete'),
    
    # Logs Dashboard
    path('logs/', views.logs_dashboard, name='logs_dashboard'),
]

