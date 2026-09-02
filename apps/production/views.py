from common.viewsets import AuditedModelViewSet
from apps.accounts.permissions import HasModulePermission
from .models import ProductionBatch
from .serializers import ProductionBatchSerializer
from .services import complete_production, reverse_production
from .services import calculate_production_requirements
from apps.master_data.models import FinishedProduct
from apps.locations.models import Location
from apps.recipes.models import Recipe
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from decimal import Decimal, InvalidOperation
from rest_framework.decorators import action
from rest_framework.response import Response
from common.idempotency import idempotent_action
class ProductionBatchViewSet(AuditedModelViewSet):
 queryset=ProductionBatch.objects.all();serializer_class=ProductionBatchSerializer;permission_classes=[HasModulePermission];module_name="production"
 @action(detail=True,methods=["post"])
 @idempotent_action
 def complete(self,request,pk=None):
  return Response({"success":True,"data":self.get_serializer(complete_production(pk,request.user,request.data.get("actual_quantity"))).data})
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None):
  return Response({"success":True,"data":self.get_serializer(reverse_production(pk,request.user,request.data.get("reason",""))).data})


class ProductionRequirementsView(APIView):
    permission_classes = [IsAuthenticated, HasModulePermission]
    module_name = "production"

    def get(self, request):
        product_id = request.query_params.get("finished_product")
        recipe_id = request.query_params.get("recipe")
        location_id = request.query_params.get("production_location")
        try:
            requested = Decimal(str(request.query_params.get("requested_quantity", "")))
        except (InvalidOperation, TypeError):
            raise ValidationError("Requested production quantity must be a valid number.")
        if requested <= 0:
            raise ValidationError("Requested production quantity must be greater than zero.")
        try:
            product = FinishedProduct.objects.get(pk=product_id, status="ACTIVE")
        except (FinishedProduct.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Active finished product was not found.")
        try:
            recipe = Recipe.objects.prefetch_related("items").get(pk=recipe_id, finished_product=product)
        except (Recipe.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Recipe was not found for the selected product.")
        try:
            location = Location.objects.get(pk=location_id, location_type="PRODUCTION", is_active=True)
        except (Location.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Active production location was not found.")
        user = request.user
        if user.role != "ADMINISTRATOR" and not user.can_access_all_locations and user.assigned_location_id and user.assigned_location_id != location.id:
            return Response({"detail": "You do not have access to this production location."}, status=403)
        requirements = calculate_production_requirements(recipe, requested, location)
        shortages = [item for item in requirements if not item["sufficient"]]
        return Response({
            "finished_product": {"id": str(product.id), "product_code": product.product_code, "name": product.name, "sales_unit": str(product.sales_unit_id)},
            "recipe": {"id": str(recipe.id), "recipe_number": recipe.recipe_number, "standard_output_quantity": recipe.standard_output_quantity, "output_unit": str(recipe.output_unit_id), "version": recipe.version},
            "requested_quantity": requested,
            "production_location": {"id": str(location.id), "code": location.code, "name": location.name, "location_type": location.location_type},
            "can_produce": not shortages,
            "requirements": requirements,
            "shortages": shortages,
        })
