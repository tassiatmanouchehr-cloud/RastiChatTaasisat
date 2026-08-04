from django.urls import path, include
from rest_framework.routers import DefaultRouter
from common.views import HealthCheckView
from conversations.views import CustomerConversationViewSet, PlatformSupportViewSet, WorkspaceSupportViewSet, StartCustomerChatView, MessageListView, SendMessageView

router = DefaultRouter()
router.register(r'conversations/customer', CustomerConversationViewSet, basename='customer-conv')
router.register(r'support', WorkspaceSupportViewSet, basename='ws-support')
router.register(r'platform/support', PlatformSupportViewSet, basename='pl-support')

urlpatterns = [
    path('auth/', include('accounts.urls')),
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('widget/init/', include('visitors.urls')),
    path('widget/start/', StartCustomerChatView.as_view(), name='widget-start'),
    path('', include(router.urls)),
    path('conversations/<uuid:conv_id>/messages/', MessageListView.as_view(), name='message-list'),
    path('conversations/<uuid:conv_id>/send/', SendMessageView.as_view(), name='message-send'),
]
