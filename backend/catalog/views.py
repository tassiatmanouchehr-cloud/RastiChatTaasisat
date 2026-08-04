from rest_framework import viewsets
from .models import Product
from .serializers import ProductSerializer
from common.permissions import IsWorkspaceOperator


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsWorkspaceOperator]

    def get_queryset(self):
        return Product.objects.filter(workspace__memberships__user=self.request.user, is_active=True)

    def perform_create(self, serializer):
        membership = self.request.user.workspace_memberships.first()
        serializer.save(workspace=membership.workspace)
