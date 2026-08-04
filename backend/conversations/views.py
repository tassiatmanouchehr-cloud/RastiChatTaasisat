from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from .models import Conversation, Message, MessageReceipt, Assignment
from .serializers import ConversationSerializer, MessageSerializer
from common.permissions import IsWorkspaceOperator, IsWorkspaceAdmin, IsPlatformSupportAgent
from visitors.models import Visitor, VisitorSession
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from audit.models import AuditEvent

class CustomerConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsWorkspaceOperator]
    def get_queryset(self):
        return Conversation.objects.filter(workspace__memberships__user=self.request.user, type=Conversation.Type.CUSTOMER)
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conv = self.get_object()
        msgs = conv.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True).data)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        conv = self.get_object()
        for msg in conv.messages.exclude(receipts__user=request.user):
            MessageReceipt.objects.create(message=msg, user=request.user)
        return Response(status=200)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        conv = self.get_object(); conv.assigned_to = request.user; conv.status = Conversation.Status.OPEN; conv.save()
        return Response(ConversationSerializer(conv).data)
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        conv = self.get_object(); conv.status = Conversation.Status.CLOSED; conv.save()
        return Response(ConversationSerializer(conv).data)

class StartCustomerChatView(APIView):
    permission_classes = []
    def post(self, request):
        from django.core.exceptions import ValidationError
        try:
            session = VisitorSession.objects.get(token=request.data.get('session_token'))
        except (VisitorSession.DoesNotExist, ValidationError):
            return Response({'error': 'Invalid session'}, status=status.HTTP_401_UNAUTHORIZED)
        conv, created = Conversation.objects.get_or_create(visitor=session.visitor, workspace=session.visitor.project.workspace, type=Conversation.Type.CUSTOMER, status=Conversation.Status.OPEN)
        if not created and conv.status == 'CLOSED': conv.status = 'OPEN'; conv.save()
        return Response(ConversationSerializer(conv).data, status=200)

class MessageListView(APIView):
    permission_classes = [IsWorkspaceOperator]
    def get(self, request, conv_id):
        try:
            conv = Conversation.objects.get(id=conv_id, workspace__memberships__user=request.user)
        except Conversation.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        msgs = conv.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True).data)

class SendMessageView(APIView):
    permission_classes = [IsWorkspaceOperator]
    def post(self, request, conv_id):
        content = request.data.get('content', '').strip()
        if not content: return Response({'error': 'Empty message'}, status=status.HTTP_400_BAD_REQUEST)
        if len(content) > 5000: return Response({'error': 'Message too long'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            conv = Conversation.objects.get(id=conv_id, workspace__memberships__user=request.user)
        except Conversation.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        client_msg_id = request.data.get('client_message_id')
        if not client_msg_id: return Response({'error': 'Missing client_message_id'}, status=status.HTTP_400_BAD_REQUEST)
        if Message.objects.filter(conversation=conv, client_message_id=client_msg_id).exists():
            return Response({'error': 'Duplicate message'}, status=status.HTTP_409_CONFLICT)
        msg = Message.objects.create(conversation=conv, sender=request.user, sender_type=Message.SenderType.USER, content=content, client_message_id=client_msg_id)
        async_to_sync(get_channel_layer().group_send)(f"chat_{conv_id}", {'type': 'chat.message', 'message': {'id': str(msg.id), 'sender_type': 'USER', 'content': msg.content, 'created_at': msg.created_at.isoformat()}})
        return Response(MessageSerializer(msg).data, status=201)

# --- PLATFORM SUPPORT VIEWS ---

class WorkspaceSupportViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsWorkspaceAdmin]

    def get_queryset(self):
        return Conversation.objects.filter(workspace__memberships__user=self.request.user, type=Conversation.Type.PLATFORM_SUPPORT)

    def create(self, request, *args, **kwargs):
        ws = request.user.workspace_memberships.filter(role__in=['WORKSPACE_OWNER', 'WORKSPACE_ADMIN']).first()
        if not ws: return Response({'error': 'Not admin'}, status=403)
        conv = Conversation.objects.create(
            workspace=ws.workspace, type=Conversation.Type.PLATFORM_SUPPORT, 
            status=Conversation.Status.WAITING_FOR_PLATFORM, subject=request.data.get('subject', 'Support')
        )
        AuditEvent.objects.create(actor=request.user, action='support_conversation_created', target_type='conversation', target_id=str(conv.id))
        return Response(ConversationSerializer(conv).data, status=201)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conv = self.get_object()
        msgs = conv.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True).data)

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        conv = self.get_object()
        content = request.data.get('content', '').strip()
        if not content: return Response({'error': 'Empty'}, status=400)
        if len(content) > 5000: return Response({'error': 'Too long'}, status=400)
        
        client_msg_id = request.data.get('client_message_id')
        if Message.objects.filter(conversation=conv, client_message_id=client_msg_id).exists():
            return Response({'error': 'Duplicate'}, status=409)
            
        msg = Message.objects.create(conversation=conv, sender=request.user, sender_type=Message.SenderType.USER, content=content, client_message_id=client_msg_id)
        conv.status = Conversation.Status.WAITING_FOR_PLATFORM
        conv.save()
        
        async_to_sync(get_channel_layer().group_send)(f"support_chat_{conv.id}", {'type': 'chat.message', 'message': {'id': str(msg.id), 'sender_type': 'USER', 'content': msg.content, 'created_at': msg.created_at.isoformat()}})
        return Response(MessageSerializer(msg).data, status=201)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        conv = self.get_object()
        for msg in conv.messages.exclude(receipts__user=request.user):
            MessageReceipt.objects.create(message=msg, user=request.user)
        return Response(status=200)

class PlatformSupportViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsPlatformSupportAgent]

    def get_queryset(self):
        return Conversation.objects.filter(workspace__platform__memberships__user=self.request.user, type=Conversation.Type.PLATFORM_SUPPORT)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conv = self.get_object()
        msgs = conv.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True).data)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        conv = self.get_object()
        for msg in conv.messages.exclude(receipts__user=request.user):
            MessageReceipt.objects.create(message=msg, user=request.user)
        return Response(status=200)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        conv = self.get_object()
        # Ensure agent belongs to the same platform
        if not request.user.platform_memberships.filter(platform=conv.workspace.platform).exists():
            return Response({'error': 'Cross-platform assignment denied'}, status=403)
        
        conv.assigned_to = request.user
        Assignment.objects.create(conversation=conv, assigned_to=request.user, assigned_by=request.user)
        AuditEvent.objects.create(actor=request.user, action='support_conversation_assigned', target_type='conversation', target_id=str(conv.id))
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        conv = self.get_object()
        content = request.data.get('content', '').strip()
        if not content: return Response({'error': 'Empty'}, status=400)
        
        msg = Message.objects.create(conversation=conv, sender=request.user, sender_type=Message.SenderType.USER, content=content, client_message_id=request.data['client_message_id'])
        conv.status = Conversation.Status.WAITING_FOR_WORKSPACE
        conv.save()
        
        async_to_sync(get_channel_layer().group_send)(f"support_chat_{conv.id}", {'type': 'chat.message', 'message': {'id': str(msg.id), 'sender_type': 'USER', 'content': msg.content, 'created_at': msg.created_at.isoformat()}})
        return Response(MessageSerializer(msg).data, status=201)
