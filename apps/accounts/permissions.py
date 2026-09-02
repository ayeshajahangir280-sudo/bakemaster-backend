from rest_framework.permissions import BasePermission
class IsAdministrator(BasePermission):
    def has_permission(self,request,view): return bool(request.user.is_authenticated and request.user.role=="ADMINISTRATOR")
class HasModulePermission(BasePermission):
    def has_permission(self,request,view): return bool(request.user.is_authenticated and request.user.has_module(getattr(view,"module_name","")))
class HasLocationAccess(BasePermission):
    def has_object_permission(self,request,view,obj):
        u=request.user
        if u.role=="ADMINISTRATOR" or u.can_access_all_locations:return True
        loc=getattr(obj,"sales_location",None) or getattr(obj,"warehouse",None) or getattr(obj,"location",None) or getattr(obj,"assigned_location",None)
        return loc is None or loc==u.assigned_location
class CanPostTransaction(HasModulePermission): pass
class CanCancelTransaction(HasModulePermission): pass
class CanApproveTransaction(HasModulePermission): pass
