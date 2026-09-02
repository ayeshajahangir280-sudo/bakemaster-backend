from rest_framework import generics,status,viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User
from .permissions import HasModulePermission
from .serializers import LoginSerializer,UserSerializer,UserAdminSerializer,ResetUserPasswordSerializer,ChangePasswordSerializer
from drf_spectacular.utils import OpenApiTypes,extend_schema,inline_serializer
from rest_framework import serializers
class LoginView(TokenObtainPairView): permission_classes=[AllowAny]; serializer_class=LoginSerializer
class MeView(APIView):
    @extend_schema(operation_id="auth_me",responses=UserSerializer)
    def get(self,request): return Response({"success":True,"data":UserSerializer(request.user).data})
class LogoutView(APIView):
    @extend_schema(operation_id="auth_logout",request=inline_serializer("LogoutRequest",fields={"refresh":serializers.CharField()}),responses={200:OpenApiTypes.OBJECT})
    def post(self,request):
        RefreshToken(request.data["refresh"]).blacklist(); return Response({"success":True,"message":"Logged out."})
class ChangePasswordView(generics.GenericAPIView):
    serializer_class=ChangePasswordSerializer
    def post(self,request):
        s=self.get_serializer(data=request.data); s.is_valid(raise_exception=True); request.user.set_password(s.validated_data["new_password"]); request.user.save(update_fields=["password"]); return Response({"success":True,"message":"Password changed."})
class UserAdminViewSet(viewsets.ModelViewSet):
    queryset=User.objects.order_by("full_name","email")
    serializer_class=UserAdminSerializer
    permission_classes=[HasModulePermission]
    module_name="users"
    @action(detail=True,methods=["post"],url_path="reset-password")
    def reset_password(self,request,pk=None):
        serializer=ResetUserPasswordSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        user=self.get_object(); user.set_password(serializer.validated_data["password"]); user.save(update_fields=["password"])
        return Response({"success":True,"message":"Password reset."})
