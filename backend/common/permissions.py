from rest_framework import permissions

class IsPlatformOwner(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.platform_memberships.filter(role='PLATFORM_OWNER').exists()

class IsPlatformAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.platform_memberships.filter(role__in=['PLATFORM_OWNER', 'PLATFORM_ADMIN']).exists()

class IsPlatformSupportAgent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.platform_memberships.filter(role__in=['PLATFORM_OWNER', 'PLATFORM_ADMIN', 'PLATFORM_SUPPORT_AGENT']).exists()

class IsWorkspaceOwner(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.workspace_memberships.filter(role='WORKSPACE_OWNER').exists()

class IsWorkspaceAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.workspace_memberships.filter(role__in=['WORKSPACE_OWNER', 'WORKSPACE_ADMIN']).exists()

class IsWorkspaceOperator(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.workspace_memberships.filter(role__in=['WORKSPACE_OWNER', 'WORKSPACE_ADMIN', 'WORKSPACE_OPERATOR']).exists()

class IsSupervisorOrAdmin(permissions.BasePermission):
    """Workspace Owner/Admin, or a team SUPERVISOR-role member — never a
    regular operator. Used for the supervisor operational dashboard so
    ordinary agents can't see or act on other agents' workloads.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.workspace_memberships.filter(role__in=['WORKSPACE_OWNER', 'WORKSPACE_ADMIN']).exists():
            return True
        from teams.models import TeamMembership
        return TeamMembership.objects.filter(user=request.user, role='SUPERVISOR', is_active=True).exists()
