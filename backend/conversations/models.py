import uuid
from django.db import models
from django.conf import settings
from projects.models import Project
from workspaces.models import Workspace
from visitors.models import Visitor

class Conversation(models.Model):
    class Type(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer Support'
        PLATFORM_SUPPORT = 'PLATFORM_SUPPORT', 'Platform Support'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        PENDING = 'PENDING', 'Pending'
        CLOSED = 'CLOSED', 'Closed'
        WAITING_FOR_WORKSPACE = 'WAITING_FOR_WORKSPACE', 'Waiting for Workspace'
        WAITING_FOR_PLATFORM = 'WAITING_FOR_PLATFORM', 'Waiting for Platform'
        RESOLVED = 'RESOLVED', 'Resolved'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN)
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='conversations')
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='conversations')
    
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True)
    
    subject = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=100, blank=True)
    
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_conversations')
    
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Message(models.Model):
    class SenderType(models.TextChoices):
        VISITOR = 'VISITOR', 'Visitor'
        USER = 'USER', 'User'
        SYSTEM = 'SYSTEM', 'System'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender_type = models.CharField(max_length=10, choices=SenderType.choices)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    sender_visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField()
    client_message_id = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('conversation', 'client_message_id')
        ordering = ['created_at']

class MessageReceipt(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='receipts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, null=True, blank=True)
    read_at = models.DateTimeField(auto_now_add=True)

class Assignment(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='assignment_history')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='assignments_made')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
