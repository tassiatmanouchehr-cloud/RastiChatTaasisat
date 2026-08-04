from django.urls import path, include
from rest_framework.routers import DefaultRouter
from common.views import HealthCheckView
from conversations.views import (
    CustomerConversationViewSet, PlatformSupportViewSet, WorkspaceSupportViewSet,
    StartCustomerChatView, MessageListView, SendMessageView,
    WidgetMessageListView, WidgetMarkReadView, WidgetUploadView, WidgetRateConversationView,
)
from catalog.views import ProductViewSet
from customer_context.views import (
    TagViewSet, ConversationTagsView, ConversationNotesView, CustomerContextView,
)

router = DefaultRouter()
router.register(r'conversations/customer', CustomerConversationViewSet, basename='customer-conv')
router.register(r'support', WorkspaceSupportViewSet, basename='ws-support')
router.register(r'platform/support', PlatformSupportViewSet, basename='pl-support')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'tags', TagViewSet, basename='tag')

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
    path('widget/conversations/<uuid:conv_id>/messages/', WidgetMessageListView.as_view(), name='widget-message-list'),
    path('widget/conversations/<uuid:conv_id>/mark_read/', WidgetMarkReadView.as_view(), name='widget-mark-read'),
    path('widget/conversations/<uuid:conv_id>/upload/', WidgetUploadView.as_view(), name='widget-upload'),
    path('widget/conversations/<uuid:conv_id>/rate/', WidgetRateConversationView.as_view(), name='widget-rate'),
]
