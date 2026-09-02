import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
class UserManager(BaseUserManager):
    def create_user(self,email,password=None,**extra):
        if not email: raise ValueError("Email is required")
        user=self.model(email=self.normalize_email(email),**extra); user.set_password(password); user.save(using=self._db); return user
    def create_superuser(self,email,password=None,**extra):
        extra.update(role="ADMINISTRATOR",is_staff=True,is_superuser=True,can_access_all_locations=True)
        return self.create_user(email,password,**extra)
class User(AbstractBaseUser,PermissionsMixin):
    class Role(models.TextChoices):
        ADMINISTRATOR="ADMINISTRATOR","Administrator"; PURCHASE="PURCHASE","Purchase"; PRODUCTION="PRODUCTION","Production"; WAREHOUSE="WAREHOUSE","Warehouse"; SALES="SALES","Sales"; ACCOUNTS="ACCOUNTS","Accounts"; MANAGER="MANAGER","Manager"
    MODULES=[(x,x.replace("_"," ").title()) for x in ("dashboard","purchasing","suppliers","supplier_payments","raw_materials","inventory","stock_adjustments","material_transfers","recipes","production","wastage","finished_goods","stock_transfers","sales","customers","customer_payments","sales_returns","reports","users","settings","audit")]
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); email=models.EmailField(unique=True); full_name=models.CharField(max_length=160); employee_code=models.CharField(max_length=40,unique=True); role=models.CharField(max_length=30,choices=Role.choices); department=models.CharField(max_length=120,blank=True)
    assigned_location=models.ForeignKey("locations.Location",null=True,blank=True,on_delete=models.SET_NULL,related_name="users"); can_access_all_locations=models.BooleanField(default=False); allowed_modules=models.JSONField(default=list,blank=True); can_override_negative_stock=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True); is_staff=models.BooleanField(default=False); date_joined=models.DateTimeField(auto_now_add=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    USERNAME_FIELD="email"; REQUIRED_FIELDS=["full_name","employee_code"]; objects=UserManager()
    def has_module(self,module): return self.role==self.Role.ADMINISTRATOR or module in self.allowed_modules
    def __str__(self): return self.email
