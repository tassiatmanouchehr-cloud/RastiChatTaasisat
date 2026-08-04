import json
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.throttling import ScopedRateThrottle
from .models import Conversation, Message, MessageReceipt, Assignment
from .serializers import ConversationSerializer, MessageSerializer
from .media_validation import validate_and_normalize_upload, UploadValidationError
from common.permissions import IsWorkspaceOperator, IsWorkspaceAdmin, IsPlatformSupportAgent
from visitors.models import Visitor, VisitorSession
from catalog.models import Product
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from audit.models import AuditEvent
from .branding import build_widget_branding

User = get_user_model()


def _broadcast(conv_id, message_data, group_prefix='chat'):
    # The channel layer serializes with msgpack, which chokes on non-primitive
    # types (e.g. the UUID a DRF PrimaryKeyRelatedField returns for `conversation`).
    # Round-tripping through JSON guarantees a msgpack-safe, plain-primitive payload.
    safe_data = json.loads(json.dumps(dict(message_data), default=str))
    async_to_sync(get_channel_layer().group_send)(
        f"{group_prefix}_{conv_id}", {'type': 'chat.message', 'message': safe_data}
    )


def _broadcast_seen(conv_id, reader, group_prefix='chat'):
    async_to_sync(get_channel_layer().group_send)(
        f"{group_prefix}_{conv_id}", {'type': 'message.seen', 'reader': reader}
    )


def _broadcast_branding(conv):
    async_to_sync(get_channel_layer().group_send)(
        f"chat_{conv.id}", {'type': 'branding.updated', 'branding': build_widget_branding(conv)}
    )


class CustomerConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsWorkspaceOperator]
    throttle_scope = 'media_upload'  # only consulted by the `upload` action's ScopedRateThrottle
    def get_queryset(self):
        return Conversation.objects.filter(workspace__memberships__user=self.request.user, type=Conversation.Type.CUSTOMER)
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conv = self.get_object()
        msgs = conv.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        conv = self.get_object()
        for msg in conv.messages.exclude(receipts__user=request.user):
            MessageReceipt.objects.create(message=msg, user=request.user)
        _broadcast_seen(conv.id, 'USER')
        return Response(status=200)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign (or reassign) the conversation to an operator.

        With no `operator_id`, self-assigns the requesting operator (the
        existing "واگذاری به من" behavior). With an `operator_id`, reassigns
        to that operator instead — but only if they're a member of the same
        workspace, so an operator can never assign a conversation to someone
        outside their own tenant.
        """
        conv = self.get_object()
        operator_id = request.data.get('operator_id')
        if operator_id:
            try:
                target = User.objects.get(
                    id=operator_id, workspace_memberships__workspace=conv.workspace,
                )
            except (User.DoesNotExist, DjangoValidationError, ValueError):
                return Response({'error': 'Operator not found in this workspace'}, status=status.HTTP_404_NOT_FOUND)
            conv.assigned_to = target
        else:
            conv.assigned_to = request.user
        conv.status = Conversation.Status.OPEN
        conv.save()
        _broadcast_branding(conv)
        return Response(ConversationSerializer(conv, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        conv = self.get_object()
        conv.status = Conversation.Status.CLOSED
        conv.closed_at = timezone.now()
        conv.save()
        return Response(ConversationSerializer(conv, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        conv = self.get_object()
        if conv.status != Conversation.Status.CLOSED:
            return Response({'error': 'Conversation is not closed'}, status=status.HTTP_400_BAD_REQUEST)
        conv.status = Conversation.Status.OPEN
        conv.closed_at = None
        conv.save()
        return Response(ConversationSerializer(conv, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def teammates(self, request, pk=None):
        """Workspace operators this conversation can be (re)assigned to."""
        conv = self.get_object()
        operators = User.objects.filter(workspace_memberships__workspace=conv.workspace).distinct()
        return Response([
            {'id': str(u.id), 'display_name': u.display_name or u.email.split('@')[0], 'email': u.email}
            for u in operators
        ])

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser],
            throttle_classes=[ScopedRateThrottle])
    def upload(self, request, pk=None):
        conv = self.get_object()
        message_type = request.data.get('message_type', Message.MessageType.IMAGE)
        if message_type not in (Message.MessageType.IMAGE, Message.MessageType.VOICE):
            return Response({'error': 'Invalid message_type'}, status=status.HTTP_400_BAD_REQUEST)
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Missing file'}, status=status.HTTP_400_BAD_REQUEST)
        client_msg_id = request.data.get('client_message_id')
        if not client_msg_id:
            return Response({'error': 'Missing client_message_id'}, status=status.HTTP_400_BAD_REQUEST)
        if Message.objects.filter(conversation=conv, client_message_id=client_msg_id).exists():
            return Response({'error': 'Duplicate message'}, status=status.HTTP_409_CONFLICT)
        try:
            file = validate_and_normalize_upload(file, message_type)
        except UploadValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        metadata = {}
        caption = (request.data.get('caption') or '').strip()
        if caption:
            metadata['caption'] = caption
        duration = request.data.get('duration')
        if duration:
            metadata['duration'] = duration
        msg = Message.objects.create(
            conversation=conv, sender=request.user, sender_type=Message.SenderType.USER,
            content='', client_message_id=client_msg_id, message_type=message_type,
            metadata=metadata, attachment=file,
        )
        data = MessageSerializer(msg, context={'request': request}).data
        _broadcast(conv.id, data)
        return Response(data, status=201)

    @action(detail=True, methods=['post'])
    def share_product(self, request, pk=None):
        conv = self.get_object()
        client_msg_id = request.data.get('client_message_id')
        if not client_msg_id:
            return Response({'error': 'Missing client_message_id'}, status=status.HTTP_400_BAD_REQUEST)
        if Message.objects.filter(conversation=conv, client_message_id=client_msg_id).exists():
            return Response({'error': 'Duplicate message'}, status=status.HTTP_409_CONFLICT)
        try:
            product = Product.objects.get(id=request.data.get('product_id'), workspace=conv.workspace)
        except (Product.DoesNotExist, ValueError, DjangoValidationError):
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
        discount_percent = 0
        if product.old_price and product.old_price > product.price:
            discount_percent = round((1 - (product.price / product.old_price)) * 100)
        metadata = {
            'product_id': str(product.id), 'brand': product.brand, 'name': product.name,
            'price': str(product.price), 'old_price': str(product.old_price) if product.old_price else None,
            'currency': product.currency, 'discount_percent': discount_percent,
            'rating': float(product.rating), 'reviews_count': product.reviews_count, 'image': product.image,
            'product_url': product.product_url, 'is_available': product.is_available,
        }
        msg = Message.objects.create(
            conversation=conv, sender=request.user, sender_type=Message.SenderType.USER,
            content='', client_message_id=client_msg_id, message_type=Message.MessageType.PRODUCT,
            metadata=metadata,
        )
        data = MessageSerializer(msg, context={'request': request}).data
        _broadcast(conv.id, data)
        return Response(data, status=201)

    @action(detail=True, methods=['post'])
    def request_rating(self, request, pk=None):
        conv = self.get_object()
        client_msg_id = request.data.get('client_message_id') or f'rating_req_{conv.id}'
        if Message.objects.filter(conversation=conv, client_message_id=client_msg_id).exists():
            return Response({'error': 'Duplicate message'}, status=status.HTTP_409_CONFLICT)
        msg = Message.objects.create(
            conversation=conv, sender=request.user, sender_type=Message.SenderType.USER,
            content='', client_message_id=client_msg_id, message_type=Message.MessageType.RATING_REQUEST,
        )
        data = MessageSerializer(msg, context={'request': request}).data
        _broadcast(conv.id, data)
        return Response(data, status=201)

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
        data = ConversationSerializer(conv).data
        data['branding'] = build_widget_branding(conv)
        return Response(data, status=200)

class MessageListView(APIView):
    permission_classes = [IsWorkspaceOperator]
    def get(self, request, conv_id):
        try:
            conv = Conversation.objects.get(id=conv_id, workspace__memberships__user=request.user)
        except Conversation.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        msgs = conv.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True, context={'request': request}).data)

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
        data = MessageSerializer(msg, context={'request': request}).data
        _broadcast(conv_id, data)
        return Response(data, status=201)

# --- WIDGET (VISITOR-FACING) RICH MESSAGE VIEWS ---
# These mirror the operator-side endpoints above but authenticate via the
# visitor's session_token instead of a JWT, matching StartCustomerChatView.

def _get_visitor_conversation(session_token, conv_id):
    session = VisitorSession.objects.get(token=session_token)
    return Conversation.objects.get(id=conv_id, visitor=session.visitor, type=Conversation.Type.CUSTOMER)

class WidgetMessageListView(APIView):
    permission_classes = []
    def get(self, request, conv_id):
        try:
            conv = _get_visitor_conversation(request.query_params.get('session_token'), conv_id)
        except (VisitorSession.DoesNotExist, Conversation.DoesNotExist, DjangoValidationError, ValueError):
            return Response(status=status.HTTP_404_NOT_FOUND)
        msgs = conv.messages.all().order_by('created_at')
        return Response(MessageSerializer(msgs, many=True, context={'request': request}).data)

class WidgetBrandingView(APIView):
    """Lets the widget re-fetch store/consultant branding on demand (e.g.
    after a reconnect where a live `branding.updated` WS event may have been
    missed while disconnected).
    """
    permission_classes = []
    def get(self, request, conv_id):
        try:
            conv = _get_visitor_conversation(request.query_params.get('session_token'), conv_id)
        except (VisitorSession.DoesNotExist, Conversation.DoesNotExist, DjangoValidationError, ValueError):
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(build_widget_branding(conv))

class WidgetMarkReadView(APIView):
    permission_classes = []
    def post(self, request, conv_id):
        try:
            conv = _get_visitor_conversation(request.data.get('session_token'), conv_id)
        except (VisitorSession.DoesNotExist, Conversation.DoesNotExist, DjangoValidationError, ValueError):
            return Response(status=status.HTTP_404_NOT_FOUND)
        for msg in conv.messages.exclude(receipts__visitor=conv.visitor).exclude(sender_type=Message.SenderType.VISITOR):
            MessageReceipt.objects.create(message=msg, visitor=conv.visitor)
        _broadcast_seen(conv.id, 'VISITOR')
        return Response(status=200)

class WidgetUploadView(APIView):
    permission_classes = []
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'media_upload'
    def post(self, request, conv_id):
        try:
            conv = _get_visitor_conversation(request.data.get('session_token'), conv_id)
        except (VisitorSession.DoesNotExist, Conversation.DoesNotExist, DjangoValidationError, ValueError):
            return Response(status=status.HTTP_404_NOT_FOUND)
        message_type = request.data.get('message_type', Message.MessageType.IMAGE)
        if message_type not in (Message.MessageType.IMAGE, Message.MessageType.VOICE):
            return Response({'error': 'Invalid message_type'}, status=status.HTTP_400_BAD_REQUEST)
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Missing file'}, status=status.HTTP_400_BAD_REQUEST)
        client_msg_id = request.data.get('client_message_id')
        if not client_msg_id:
            return Response({'error': 'Missing client_message_id'}, status=status.HTTP_400_BAD_REQUEST)
        if Message.objects.filter(conversation=conv, client_message_id=client_msg_id).exists():
            return Response({'error': 'Duplicate message'}, status=status.HTTP_409_CONFLICT)
        try:
            file = validate_and_normalize_upload(file, message_type)
        except UploadValidationError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        metadata = {}
        caption = (request.data.get('caption') or '').strip()
        if caption:
            metadata['caption'] = caption
        duration = request.data.get('duration')
        if duration:
            metadata['duration'] = duration
        msg = Message.objects.create(
            conversation=conv, sender_type=Message.SenderType.VISITOR, sender_visitor=conv.visitor,
            content='', client_message_id=client_msg_id, message_type=message_type,
            metadata=metadata, attachment=file,
        )
        data = MessageSerializer(msg, context={'request': request}).data
        _broadcast(conv.id, data)
        return Response(data, status=201)

class WidgetRateConversationView(APIView):
    permission_classes = []
    def post(self, request, conv_id):
        try:
            conv = _get_visitor_conversation(request.data.get('session_token'), conv_id)
        except (VisitorSession.DoesNotExist, Conversation.DoesNotExist, DjangoValidationError, ValueError):
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            rating = int(request.data.get('rating'))
        except (TypeError, ValueError):
            return Response({'error': 'Invalid rating'}, status=status.HTTP_400_BAD_REQUEST)
        if rating < 1 or rating > 5:
            return Response({'error': 'Rating must be between 1 and 5'}, status=status.HTTP_400_BAD_REQUEST)
        if conv.rating is not None:
            return Response(
                {'error': 'Conversation has already been rated'},
                status=status.HTTP_409_CONFLICT,
            )
        client_msg_id = request.data.get('client_message_id') or f'rating_{conv.id}'
        if Message.objects.filter(conversation=conv, client_message_id=client_msg_id).exists():
            return Response({'error': 'Duplicate message'}, status=status.HTTP_409_CONFLICT)
        msg = Message.objects.create(
            conversation=conv, sender_type=Message.SenderType.VISITOR, sender_visitor=conv.visitor,
            content='', client_message_id=client_msg_id, message_type=Message.MessageType.RATING,
            metadata={'rating': rating},
        )
        _broadcast(conv.id, MessageSerializer(msg, context={'request': request}).data)
        conv.rating = rating
        conv.save(update_fields=['rating'])
        return Response(ConversationSerializer(conv).data, status=200)

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
