from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import connections
from django.core.cache import cache

class HealthCheckView(APIView):
    permission_classes = []
    def get(self, request):
        health = {'status': 'healthy', 'components': {}}
        
        try:
            connections['default'].cursor()
            health['components']['database'] = 'up'
        except Exception:
            health['components']['database'] = 'down'
            health['status'] = 'unhealthy'
            
        try:
            cache.set('health_test', '1', timeout=1)
            health['components']['redis'] = 'up'
        except Exception:
            health['components']['redis'] = 'down'
            health['status'] = 'unhealthy'
            
        status_code = 200 if health['status'] == 'healthy' else 503
        return Response(health, status=status_code)
