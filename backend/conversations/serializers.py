from rest_framework import serializers
from .models import Conversation, Message

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender_type', 'content', 'client_message_id', 'created_at']
        read_only_fields = ['id', 'created_at', 'sender_type', 'conversation']

class ConversationSerializer(serializers.ModelSerializer):
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'type', 'status', 'subject', 'created_at', 'updated_at', 'unread_count']
        read_only_fields = ['id', 'type', 'status', 'created_at', 'updated_at', 'unread_count']

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        return obj.messages.exclude(receipts__user=request.user).count()
