from django.urls import path, include
from rest_framework.routers import DefaultRouter
from common.views import HealthCheckView
from conversations.views import (
    CustomerConversationViewSet, PlatformSupportViewSet, WorkspaceSupportViewSet,
    StartCustomerChatView, MessageListView, SendMessageView,
    WidgetMessageListView, WidgetMarkReadView, WidgetUploadView, WidgetRateConversationView,
    WidgetBrandingView, OperationalSummaryView,
)
from catalog.views import ProductViewSet
from customer_context.views import (
    TagViewSet, ConversationTagsView, ConversationNotesView, CustomerContextView,
)
from teams.views import TeamViewSet
from queues.views import QueueViewSet
from sla.views import BusinessCalendarViewSet, SLAPolicyViewSet, ConversationSLAView
from collaboration.views import QuickReplyViewSet
from notifications.views import NotificationViewSet
from automations.views import (
    AutomationRuleViewSet, RuleValidationView, RuleSimulationView, AutomationRegistryView,
    AutomationExecutionListView, ScheduledActionListView, ScheduledActionCancelView,
)

router = DefaultRouter()
router.register(r'conversations/customer', CustomerConversationViewSet, basename='customer-conv')
router.register(r'support', WorkspaceSupportViewSet, basename='ws-support')
router.register(r'platform/support', PlatformSupportViewSet, basename='pl-support')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'teams', TeamViewSet, basename='team')
router.register(r'queues', QueueViewSet, basename='queue')
router.register(r'business-calendars', BusinessCalendarViewSet, basename='business-calendar')
router.register(r'sla-policies', SLAPolicyViewSet, basename='sla-policy')
router.register(r'quick-replies', QuickReplyViewSet, basename='quick-reply')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'automations/rules', AutomationRuleViewSet, basename='automation-rule')

urlpatterns = [
    path('auth/', include('accounts.urls')),
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('widget/init/', include('visitors.urls')),
    path('widget/start/', StartCustomerChatView.as_view(), name='widget-start'),
    path('', include(router.urls)),
    path('conversations/<uuid:conv_id>/messages/', MessageListView.as_view(), name='message-list'),
    path('conversations/<uuid:conv_id>/send/', SendMessageView.as_view(), name='message-send'),
    path('conversations/customer/<uuid:conv_id>/tags/', ConversationTagsView.as_view(), name='conversation-tags'),
    path('conversations/customer/<uuid:conv_id>/notes/', ConversationNotesView.as_view(), name='conversation-notes'),
    path('conversations/customer/<uuid:conv_id>/customer-context/', CustomerContextView.as_view(), name='customer-context'),
    path('conversations/customer/<uuid:conv_id>/sla/', ConversationSLAView.as_view(), name='conversation-sla'),
    path('supervisor/summary/', OperationalSummaryView.as_view(), name='supervisor-summary'),
    path('widget/conversations/<uuid:conv_id>/messages/', WidgetMessageListView.as_view(), name='widget-message-list'),
    path('widget/conversations/<uuid:conv_id>/mark_read/', WidgetMarkReadView.as_view(), name='widget-mark-read'),
    path('widget/conversations/<uuid:conv_id>/upload/', WidgetUploadView.as_view(), name='widget-upload'),
    path('widget/conversations/<uuid:conv_id>/rate/', WidgetRateConversationView.as_view(), name='widget-rate'),
    path('widget/conversations/<uuid:conv_id>/branding/', WidgetBrandingView.as_view(), name='widget-branding'),
    path('automations/registry/', AutomationRegistryView.as_view(), name='automation-registry'),
    path('automations/validate/', RuleValidationView.as_view(), name='automation-validate'),
    path('automations/simulate/', RuleSimulationView.as_view(), name='automation-simulate'),
    path('automations/execution-history/', AutomationExecutionListView.as_view(), name='automation-execution-history'),
    path('automations/scheduled-actions/', ScheduledActionListView.as_view(), name='automation-scheduled-actions'),
    path('automations/scheduled-actions/<uuid:pk>/cancel/', ScheduledActionCancelView.as_view(), name='automation-scheduled-action-cancel'),
]
