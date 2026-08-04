from rest_framework import serializers
from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'brand', 'name', 'price', 'old_price', 'rating', 'reviews_count', 'image', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
