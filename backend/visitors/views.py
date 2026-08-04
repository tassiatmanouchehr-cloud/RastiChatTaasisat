import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from projects.models import Project
from .models import Visitor, VisitorSession
from .serializers import VisitorInitSerializer

class InitVisitorView(APIView):
    permission_classes = [] # Public endpoint for widget

    def post(self, request):
        serializer = VisitorInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        project = Project.objects.get(public_key=serializer.validated_data['project_key'])
        
        visitor, created = Visitor.objects.get_or_create(
            project=project,
            defaults={
                'name': serializer.validated_data.get('name'),
                'email': serializer.validated_data.get('email'),
                'mobile': serializer.validated_data.get('mobile'),
            }
        )
        
        session = VisitorSession.objects.create(visitor=visitor)
        return Response({
            'visitor_id': str(visitor.id),
            'session_token': str(session.token)
        }, status=status.HTTP_200_OK)
