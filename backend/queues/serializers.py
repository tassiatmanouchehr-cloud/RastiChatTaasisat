from rest_framework import serializers
from .models import Queue


class QueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Queue
        fields = [
            'id', 'workspace', 'team', 'name', 'is_active', 'routing_priority', 'supported_categories',
            'default_priority', 'assignment_strategy', 'max_active_per_agent', 'fallback_queue',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'workspace', 'created_at', 'updated_at']
