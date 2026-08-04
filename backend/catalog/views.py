from rest_framework import viewsets
from .models import Product
from .serializers import ProductSerializer
from common.permissions import IsWorkspaceOperator
from common.tenancy import resolve_operator_workspace


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsWorkspaceOperator]

    def get_queryset(self):
        return Product.objects.filter(workspace__memberships__user=self.request.user, is_active=True)

    def perform_create(self, serializer):
        workspace_id = self.request.data.get('workspace') or self.request.data.get('workspace_id')
        workspace = resolve_operator_workspace(self.request.user, workspace_id)
        serializer.save(workspace=workspace)
