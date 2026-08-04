import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from .models import Conversation, Message, MessageReceipt
from visitors.models import VisitorSession
from workspaces.models import WorkspaceMembership
from platforms.models import PlatformMembership

User = get_user_model()

class BaseChatConsumer(AsyncJsonWebsocketConsumer):
    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if text_data:
            try: json.loads(text_data)
            except json.JSONDecodeError: return
        await super().receive(text_data, bytes_data, **kwargs)

    async def chat_message(self, event):
        await self.send_json({**event['message'], 'type': 'chat.message'})

    async def typing_indicator(self, event):
        # Don't echo the typing event back to the person who is typing.
        if event.get('origin_channel') == self.channel_name:
            return
        await self.send_json({'type': 'typing', 'sender_type': event['sender_type']})

    async def message_seen(self, event):
        await self.send_json({'type': 'message.seen', 'reader': event['reader']})

class WidgetChatConsumer(BaseChatConsumer):
    async def connect(self):
        self.session_token = self.scope['url_route']['kwargs']['session_token']
        self.conv_id = self.scope['url_route']['kwargs']['conv_id']
        self.conversation = await self._get_visitor_conversation()
        if not self.conversation: await self.close(); return
        self.group_name = f"chat_{self.conv_id}"
        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    @database_sync_to_async
    def _get_visitor_conversation(self):
        try:
            session = VisitorSession.objects.get(token=self.session_token)
            return Conversation.objects.get(id=self.conv_id, visitor=session.visitor, type=Conversation.Type.CUSTOMER)
        except Exception: return None

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'): await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content):
        msg_kind = content.get('type')
        if msg_kind == 'typing':
            await self.channel_layer.group_send(self.group_name, {'type': 'typing.indicator', 'sender_type': 'VISITOR', 'origin_channel': self.channel_name})
            return
        if msg_kind == 'mark_read':
            await self._mark_read()
            await self.channel_layer.group_send(self.group_name, {'type': 'message.seen', 'reader': 'VISITOR'})
            return
        msg_text = content.get('message', '').strip()
        if not msg_text or len(msg_text) > 5000: return
        msg = await self._save_visitor_message(content.get('client_message_id'), msg_text)
        if not msg: return
        await self.channel_layer.group_send(self.group_name, {'type': 'chat.message', 'message': {
            'id': str(msg.id), 'sender_type': 'VISITOR', 'content': msg.content,
            'message_type': msg.message_type, 'metadata': msg.metadata, 'attachment_url': None,
            'client_message_id': msg.client_message_id, 'created_at': msg.created_at.isoformat(),
        }})

    @database_sync_to_async
    def _save_visitor_message(self, client_msg_id, msg_text):
        if Message.objects.filter(conversation=self.conversation, client_message_id=client_msg_id).exists(): return None
        return Message.objects.create(conversation=self.conversation, sender_type=Message.SenderType.VISITOR, sender_visitor=self.conversation.visitor, content=msg_text, client_message_id=client_msg_id)

    @database_sync_to_async
    def _mark_read(self):
        for msg in self.conversation.messages.exclude(receipts__visitor=self.conversation.visitor).exclude(sender_type=Message.SenderType.VISITOR):
            MessageReceipt.objects.create(message=msg, visitor=self.conversation.visitor)

class DashboardChatConsumer(BaseChatConsumer):
    async def connect(self):
        self.token = self.scope['url_route']['kwargs']['token']
        self.conv_id = self.scope['url_route']['kwargs']['conv_id']
        self.conversation = await self._get_user_conversation()
        if not self.conversation: await self.close(); return
        self.group_name = f"chat_{self.conv_id}"
        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    @database_sync_to_async
    def _get_user_conversation(self):
        try:
            access_token = AccessToken(self.token)
            user = User.objects.get(id=access_token['user_id'])
            self.user = user  # FIX: Store user for later use
            return Conversation.objects.get(id=self.conv_id, workspace__memberships__user=user, type=Conversation.Type.CUSTOMER)
        except Exception: return None

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'): await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content):
        msg_kind = content.get('type')
        if msg_kind == 'typing':
            await self.channel_layer.group_send(self.group_name, {'type': 'typing.indicator', 'sender_type': 'USER', 'origin_channel': self.channel_name})
            return
        if msg_kind == 'mark_read':
            await self._mark_read()
            await self.channel_layer.group_send(self.group_name, {'type': 'message.seen', 'reader': 'USER'})
            return
        msg_text = content.get('message', '').strip()
        if not msg_text or len(msg_text) > 5000: return
        msg = await self._save_user_message(content.get('client_message_id'), msg_text)
        if not msg: return
        await self.channel_layer.group_send(self.group_name, {'type': 'chat.message', 'message': {
            'id': str(msg.id), 'sender_type': 'USER', 'content': msg.content,
            'message_type': msg.message_type, 'metadata': msg.metadata, 'attachment_url': None,
            'client_message_id': msg.client_message_id, 'created_at': msg.created_at.isoformat(),
        }})

    @database_sync_to_async
    def _save_user_message(self, client_msg_id, msg_text):
        if Message.objects.filter(conversation=self.conversation, client_message_id=client_msg_id).exists(): return None
        return Message.objects.create(conversation=self.conversation, sender_type=Message.SenderType.USER, sender=self.user, content=msg_text, client_message_id=client_msg_id)

    @database_sync_to_async
    def _mark_read(self):
        for msg in self.conversation.messages.exclude(receipts__user=self.user).exclude(sender_type=Message.SenderType.USER):
            MessageReceipt.objects.create(message=msg, user=self.user)

class DashboardSupportConsumer(BaseChatConsumer):
    async def connect(self):
        self.token = self.scope['url_route']['kwargs']['token']
        self.conv_id = self.scope['url_route']['kwargs']['conv_id']
        self.conversation = await self._get_support_conversation()
        if not self.conversation: await self.close(); return
        self.group_name = f"support_chat_{self.conv_id}"
        await self.accept()
        await self.channel_layer.group_add(self.group_name, self.channel_name)

    @database_sync_to_async
    def _get_support_conversation(self):
        try:
            access_token = AccessToken(self.token)
            user = User.objects.get(id=access_token['user_id'])
            conv = Conversation.objects.get(id=self.conv_id, type=Conversation.Type.PLATFORM_SUPPORT)
            # Check if user is Workspace Admin/Owner of this workspace OR Platform Support Agent of this platform
            is_ws_admin = WorkspaceMembership.objects.filter(user=user, workspace=conv.workspace, role__in=['WORKSPACE_OWNER', 'WORKSPACE_ADMIN']).exists()
            is_pl_support = PlatformMembership.objects.filter(user=user, platform=conv.workspace.platform, role__in=['PLATFORM_OWNER', 'PLATFORM_ADMIN', 'PLATFORM_SUPPORT_AGENT']).exists()
            if is_ws_admin or is_pl_support:
                self.user = user
                return conv
            return None
        except Exception: return None

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'): await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content):
        msg_text = content.get('message', '').strip()
        if not msg_text or len(msg_text) > 5000: return
        msg = await self._save_support_message(content.get('client_message_id'), msg_text)
        if not msg: return
        await self.channel_layer.group_send(self.group_name, {'type': 'chat.message', 'message': {'id': str(msg.id), 'sender_type': 'USER', 'content': msg.content, 'created_at': msg.created_at.isoformat()}})

    @database_sync_to_async
    def _save_support_message(self, client_msg_id, msg_text):
        if Message.objects.filter(conversation=self.conversation, client_message_id=client_msg_id).exists(): return None
        return Message.objects.create(conversation=self.conversation, sender_type=Message.SenderType.USER, sender=self.user, content=msg_text, client_message_id=client_msg_id)
