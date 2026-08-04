import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User
from platforms.models import Platform, PlatformMembership
from workspaces.models import Workspace, WorkspaceMembership
from projects.models import Project

print("Seeding database...")

# 1. Create Platform
platform, _ = Platform.objects.get_or_create(name='RastiChat Platform')

# 2. Create Platform Owner
po, created = User.objects.get_or_create(email='platform@rasti.com', defaults={'is_staff': True, 'is_superuser': True})
if created: po.set_password('pass1234'); po.save()
PlatformMembership.objects.get_or_create(user=po, platform=platform, defaults={'role': 'PLATFORM_OWNER'})

# 3. Create Workspace
ws, _ = Workspace.objects.get_or_create(name='Sample Workspace', defaults={'platform': platform})

# 4. Create Workspace Admin
wa, created = User.objects.get_or_create(email='admin@ws.com', defaults={'is_staff': True})
if created: wa.set_password('pass1234'); wa.save()
WorkspaceMembership.objects.get_or_create(user=wa, workspace=ws, defaults={'role': 'WORKSPACE_ADMIN'})

# 5. Create Workspace Operator
wo, created = User.objects.get_or_create(email='operator@ws.com', defaults={'is_staff': True})
if created: wo.set_password('pass1234'); wo.save()
WorkspaceMembership.objects.get_or_create(user=wo, workspace=ws, defaults={'role': 'WORKSPACE_OPERATOR'})

# 6. Create Platform Support Agent
psa, created = User.objects.get_or_create(email='support@platform.com', defaults={'is_staff': True})
if created: psa.set_password('pass1234'); psa.save()
PlatformMembership.objects.get_or_create(user=psa, platform=platform, defaults={'role': 'PLATFORM_SUPPORT_AGENT'})

# 7. Create Project
proj, _ = Project.objects.get_or_create(name='Sample Website', defaults={'workspace': ws})

print("\n=== Seed Data Created Successfully ===")
print("Operator Login   : operator@ws.com / pass1234")
print("Admin Login      : admin@ws.com / pass1234")
print("Platform Support : support@platform.com / pass1234")
print(f"Project Public Key: {proj.public_key}")
print("======================================")
