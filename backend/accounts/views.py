from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .serializers import UserSerializer, PresenceSerializer
from .presence import touch_presence

class LoginView(APIView):
    permission_classes = []
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            })
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            RefreshToken(refresh_token).blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

class PresenceView(APIView):
    """Lets an operator explicitly set their own online/away/offline status
    (e.g. the dashboard's status dropdown). Activity elsewhere (opening a
    conversation) only refreshes the timestamp — it never silently flips an
    operator who explicitly went offline back to online.
    """
    def post(self, request):
        serializer = PresenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        presence = touch_presence(request.user, explicit_status=serializer.validated_data['status'])
        return Response({'status': presence.effective_status()})

    def get(self, request):
        presence = touch_presence(request.user)
        return Response({'status': presence.effective_status()})
