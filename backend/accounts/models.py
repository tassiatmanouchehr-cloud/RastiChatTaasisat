from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)

class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    # Operator-facing identity shown to visitors in the widget (e.g. "مشاور ارشد").
    # All optional — the widget must fall back gracefully when unset, never invent a name.
    display_name = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(blank=True)
    title = models.CharField(max_length=255, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class OperatorPresence(models.Model):
    class Status(models.TextChoices):
        ONLINE = 'ONLINE', 'Online'
        AWAY = 'AWAY', 'Away'
        OFFLINE = 'OFFLINE', 'Offline'

    # Explicit, operator-set status (e.g. via the dashboard's status dropdown).
    ONLINE_STALE_AFTER = timedelta(minutes=2)
    AWAY_STALE_AFTER = timedelta(minutes=10)

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='presence')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OFFLINE)
    last_active_at = models.DateTimeField(auto_now=True)

    def touch(self, status=None):
        """Record activity (WS connect, message send, mark-read) and optionally set an explicit status."""
        if status:
            self.status = status
        else:
            self.save(update_fields=['last_active_at'])
            return
        self.save(update_fields=['status', 'last_active_at'])

    def effective_status(self):
        """Explicit OFFLINE always wins; otherwise staleness of last activity overrides a stale ONLINE/AWAY claim."""
        if self.status == self.Status.OFFLINE:
            return self.Status.OFFLINE
        age = timezone.now() - self.last_active_at
        if age > self.AWAY_STALE_AFTER:
            return self.Status.OFFLINE
        if age > self.ONLINE_STALE_AFTER:
            return self.Status.AWAY
        return self.status
