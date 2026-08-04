from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import Product
from .serializers import ProductSerializer
from common.permissions import IsWorkspaceOperator


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsWorkspaceOperator]

    def get_queryset(self):
        return Product.objects.filter(workspace__memberships__user=self.request.user, is_active=True)

    def _resolve_workspace(self):
        """Resolve the target workspace for a create, never guessing across tenants.

        Silently defaulting to the user's *first* membership would let an
        operator with access to multiple workspaces accidentally create a
        product in the wrong tenant. A workspace is only implied when the
        user has exactly one membership; otherwise it must be specified
        explicitly and is validated against the user's own memberships.
        """
        memberships = list(self.request.user.workspace_memberships.select_related('workspace').all())
        if not memberships:
            raise PermissionDenied('No workspace membership')
        workspace_id = self.request.data.get('workspace') or self.request.data.get('workspace_id')
        if workspace_id:
            for membership in memberships:
                if str(membership.workspace_id) == str(workspace_id):
                    return membership.workspace
            raise PermissionDenied('Not a member of the requested workspace')
        if len(memberships) > 1:
            raise ValidationError(
                {'workspace_id': 'Must specify a workspace_id when a member of multiple workspaces'}
            )
        return memberships[0].workspace

    def perform_create(self, serializer):
        serializer.save(workspace=self._resolve_workspace())
