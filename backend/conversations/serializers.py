from rest_framework import serializers
from .models import Conversation, Message

class MessageSerializer(serializers.ModelSerializer):
    attachment_url = serializers.SerializerMethodField()
    seen = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender_type', 'content', 'message_type', 'metadata',
            'attachment_url', 'client_message_id', 'created_at', 'seen',
        ]
        read_only_fields = [
            'id', 'created_at', 'sender_type', 'conversation', 'message_type', 'metadata',
            'attachment_url', 'seen',
        ]

    def get_attachment_url(self, obj):
        if not obj.attachment:
            return None
        request = self.context.get('request')
        url = obj.attachment.url
        return request.build_absolute_uri(url) if request else url

    def get_seen(self, obj):
        # A message is "seen" once someone from the other side of the conversation has read it.
        if obj.sender_type == Message.SenderType.VISITOR:
            return obj.receipts.filter(user__isnull=False).exists()
        return obj.receipts.filter(visitor__isnull=False).exists()

class ConversationSerializer(serializers.ModelSerializer):
    unread_count = serializers.SerializerMethodField()
    visitor = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'type', 'status', 'subject', 'category', 'notes', 'rating',
            'created_at', 'updated_at', 'unread_count', 'visitor', 'last_message',
        ]
        read_only_fields = [
            'id', 'type', 'status', 'created_at', 'updated_at', 'unread_count',
            'rating', 'visitor', 'last_message',
        ]

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        return obj.messages.exclude(receipts__user=request.user).count()

    def get_visitor(self, obj):
        if not obj.visitor:
            return None
        v = obj.visitor
        return {
            'id': str(v.id),
            'name': v.name,
            'email': v.email,
            'mobile': v.mobile,
            'created_at': v.created_at,
        }

    def get_last_message(self, obj):
        msg = obj.messages.order_by('-created_at').first()
        if not msg:
            return None
        return {
            'content': msg.content,
            'message_type': msg.message_type,
            'sender_type': msg.sender_type,
            'created_at': msg.created_at,
        }
