import uuid
from datetime import datetime, time
from decimal import Decimal
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from django.db import models, transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When
from apps.accounts.permissions import HasModulePermission
from .models import InventoryBalance,StockAdjustment,StockTransaction,WastageDocument
from .serializers import StockAdjustmentSerializer,StockTransactionSerializer,WastageDocumentSerializer
from .document_services import cancel_stock_document,generated_number,post_stock_document,transition
from common.idempotency import idempotent_action

class StockDocumentViewSet(ModelViewSet):
 permission_classes=[HasModulePermission]
 filterset_fields=["status","location","raw_material","finished_product"]
 document_class=None;number_field=None;number_prefix=None
 def get_queryset(self):
  qs=self.document_class.objects.select_related("raw_material","finished_product","location","unit").order_by("-created_at");u=self.request.user
  if getattr(self,"swagger_fake_view",False):return qs.none()
  if not getattr(u,"is_authenticated",False):return qs.none()
  if u.role!="ADMINISTRATOR" and not u.can_access_all_locations and u.assigned_location_id:qs=qs.filter(location=u.assigned_location)
  return qs
 def perform_create(self,serializer):
  serializer.save(created_by=self.request.user,**{self.number_field:generated_number(self.number_prefix)})
 def perform_destroy(self,instance):
  if instance.status!="DRAFT":raise __import__("rest_framework.exceptions",fromlist=["ValidationError"]).ValidationError("Only draft documents can be deleted.")
  instance.delete()
 def _transition(self,request,pk,target):
  obj=transition(self.document_class,pk,request.user,target);return Response(self.get_serializer(obj).data)
 @action(detail=True,methods=["post"])
 def submit(self,request,pk=None):return self._transition(request,pk,"SUBMITTED")
 @action(detail=True,methods=["post"])
 def approve(self,request,pk=None):return self._transition(request,pk,"APPROVED")
 @action(detail=True,methods=["post"])
 @idempotent_action
 def post(self,request,pk=None):
  obj=post_stock_document(self.document_class,pk,request.user);return Response(self.get_serializer(obj).data)
 @action(detail=True,methods=["post"])
 @idempotent_action
 def cancel(self,request,pk=None):
  reason=str(request.data.get("reason","")).strip()
  if not reason:return Response({"detail":"Cancellation reason is required."},status=400)
  obj=cancel_stock_document(self.document_class,pk,request.user,reason);return Response(self.get_serializer(obj).data)

class WastageDocumentViewSet(StockDocumentViewSet):
 serializer_class=WastageDocumentSerializer;module_name="wastage";document_class=WastageDocument;number_field="document_number";number_prefix="WST"

class StockAdjustmentViewSet(StockDocumentViewSet):
 serializer_class=StockAdjustmentSerializer;module_name="stock_adjustments";document_class=StockAdjustment;number_field="adjustment_number";number_prefix="ADJ"

def opening_datetime(value):
 if not value:return timezone.now()
 parsed=datetime.fromisoformat(str(value))
 if parsed.tzinfo is None:parsed=timezone.make_aware(parsed)
 return parsed
class StockTransactionViewSet(ReadOnlyModelViewSet):
 serializer_class=StockTransactionSerializer; permission_classes=[HasModulePermission]; module_name="inventory"; filterset_fields=["transaction_type","raw_material","finished_product","source_location","destination_location"]
 def get_queryset(self):
  qs=StockTransaction.objects.all().order_by("-transaction_date"); u=self.request.user
  if getattr(self,"swagger_fake_view",False):return qs.none()
  if not getattr(u,"is_authenticated",False):return qs.none()
  if u.role!="ADMINISTRATOR" and not u.can_access_all_locations and u.assigned_location_id: qs=qs.filter(models.Q(source_location=u.assigned_location)|models.Q(destination_location=u.assigned_location))
  return qs
 @action(detail=False,methods=["get"],url_path="balances")
 def balances(self,request):
  """Return one current balance per item and location; historical batches are ignored."""
  qs=InventoryBalance.objects.all();u=request.user
  if u.role!="ADMINISTRATOR" and not u.can_access_all_locations and u.assigned_location_id:qs=qs.filter(location=u.assigned_location)
  data=[{"item_type":"RM" if b.raw_material_id else "FG","item_id":str(b.raw_material_id or b.finished_product_id),"location_id":str(b.location_id),"quantity":b.current_quantity,"value":b.inventory_value,"average_cost":b.average_unit_cost,"revision":b.revision} for b in qs]
  return Response({"success":True,"data":data})
 @action(detail=False,methods=["get"],url_path="reconciliation")
 def reconciliation(self,request):
  from .posting import reconciliation_discrepancies
  if request.user.role!="ADMINISTRATOR":return Response({"detail":"Administrator access is required."},status=403)
  data=reconciliation_discrepancies();return Response({"success":True,"count":len(data),"data":data})
 @action(detail=True,methods=["post"],url_path="cancel-opening")
 @idempotent_action
 @transaction.atomic
 def cancel_opening(self,request,pk=None):
  reason=str(request.data.get("reason","")).strip()
  if not reason:return Response({"detail":"Cancellation reason is required."},status=400)
  original=StockTransaction.objects.select_for_update().get(pk=pk)
  if original.transaction_type!="OPENING_STOCK" or original.is_reversal:return Response({"detail":"Only an original opening-stock entry can be cancelled."},status=400)
  if hasattr(original,"reversal"):return Response(self.get_serializer(original.reversal).data)
  from .posting import post_movement
  item=original.raw_material or original.finished_product
  reversal,_=post_movement(item=item,location=original.destination_location,quantity=original.quantity_in,direction="OUT",transaction_number=f"REV-{original.transaction_number}",transaction_type="OPENING_STOCK_REVERSAL",reference_type=original.reference_type,reference_id=original.reference_id,unit=original.unit,user=request.user,outgoing_unit_cost=original.unit_cost,remarks=f"Opening-stock cancellation: {reason}",reversal_of=original,is_reversal=True,audit_action="Cancel opening stock")
  return Response(self.get_serializer(reversal).data)
 @action(detail=False,methods=["post"],url_path="opening-finished-goods")
 @idempotent_action
 def opening_finished_goods(self,request):
  from apps.locations.models import Location
  from apps.master_data.models import FinishedProduct
  try:
   product=FinishedProduct.objects.get(pk=request.data.get("finished_product"),status="ACTIVE")
   location=Location.objects.get(pk=request.data.get("location"),location_type="FINISHED_GOODS_WAREHOUSE",is_active=True)
   quantity=Decimal(str(request.data.get("quantity",0)))
   unit_cost=Decimal(str(request.data.get("unit_cost",product.standard_cost)))
   opening_date=opening_datetime(request.data.get("opening_date"))
   notes=str(request.data.get("notes","")).strip() or "Opening finished-goods stock"
   expiry=str(request.data.get("expiry_date","")).strip()
   if quantity<=0 or unit_cost<0: raise ValueError
  except (FinishedProduct.DoesNotExist,Location.DoesNotExist,ValueError,TypeError):
   return Response({"success":False,"message":"A valid product, finished-goods location and positive quantity are required."},status=status.HTTP_400_BAD_REQUEST)
  if StockTransaction.objects.filter(reference_type="OpeningStock",finished_product=product,destination_location=location,is_reversal=False).exists():
   return Response({"success":False,"message":"Opening stock already exists for this product and location. Use a stock adjustment instead."},status=status.HTTP_400_BAD_REQUEST)
  reference_id=uuid.uuid4()
  from .posting import post_movement
  transaction,_=post_movement(item=product,location=location,quantity=quantity,direction="IN",transaction_number=f"OPEN-FG-{reference_id}",transaction_type="OPENING_STOCK",reference_type="OpeningStock",reference_id=reference_id,unit=product.sales_unit,user=request.user,incoming_unit_cost=unit_cost,remarks=f"{notes}|EXPIRY={expiry}",audit_action="Opening stock",transaction_date=opening_date)
  return Response({"success":True,"message":"Existing finished goods added.","data":self.get_serializer(transaction).data},status=status.HTTP_201_CREATED)
 @action(detail=False,methods=["post"],url_path="adjust")
 @transaction.atomic
 def adjust(self,request):
  from apps.locations.models import Location
  from apps.master_data.models import FinishedProduct,RawMaterial
  from .services import get_available_stock,get_average_cost
  item_type=str(request.data.get("item_type","")).upper()
  model=RawMaterial if item_type=="RM" else FinishedProduct if item_type=="FG" else None
  try:
   if model is None: raise ValueError
   item=model.objects.select_for_update().get(pk=request.data.get("item"),status="ACTIVE")
   location=Location.objects.get(pk=request.data.get("location"),is_active=True)
   quantity=Decimal(str(request.data.get("quantity",0)))
   reason=str(request.data.get("reason","")).strip()
   if not quantity or not reason: raise ValueError
  except (RawMaterial.DoesNotExist,FinishedProduct.DoesNotExist,Location.DoesNotExist,ValueError,TypeError):
   return Response({"success":False,"message":"A valid active item, location, non-zero quantity and reason are required."},status=status.HTTP_400_BAD_REQUEST)
  available=get_available_stock(item,location)
  if quantity<0 and -quantity>available:
   return Response({"success":False,"message":f"Insufficient stock. Only {available} is available at this location."},status=status.HTTP_400_BAD_REQUEST)
  unit_cost=get_average_cost(item,location)
  if quantity>0 and request.data.get("unit_cost") not in (None,""):
   unit_cost=Decimal(str(request.data["unit_cost"]))
   if unit_cost<0:
    return Response({"success":False,"message":"Unit cost cannot be negative."},status=status.HTTP_400_BAD_REQUEST)
  reference_id=uuid.uuid4();incoming=quantity>0
  fields={"raw_material":item} if item_type=="RM" else {"finished_product":item}
  from .posting import post_movement
  entry,_=post_movement(item=item,location=location,quantity=abs(quantity),direction="IN" if incoming else "OUT",transaction_number=f"ADJ-{reference_id}",transaction_type="STOCK_ADJUSTMENT_IN" if incoming else "STOCK_ADJUSTMENT_OUT",reference_type="StockAdjustment",reference_id=reference_id,unit=item.base_unit if item_type=="RM" else item.sales_unit,user=request.user,incoming_unit_cost=unit_cost if incoming else None,remarks=reason,audit_action="Stock adjustment")
  return Response({"success":True,"data":self.get_serializer(entry).data},status=status.HTTP_201_CREATED)
 @action(detail=False,methods=["post"],url_path="clear-finished-goods")
 @idempotent_action
 def clear_finished_goods(self,request):
  from apps.locations.models import Location
  from apps.master_data.models import FinishedProduct
  try:
   product=FinishedProduct.objects.get(pk=request.data.get("finished_product"))
   location=Location.objects.get(pk=request.data.get("location"),is_active=True)
   reason=str(request.data.get("reason","")).strip() or "Removed from finished-goods inventory"
  except (FinishedProduct.DoesNotExist,Location.DoesNotExist,ValueError,TypeError):
   return Response({"success":False,"message":"A valid product and location are required."},status=status.HTTP_400_BAD_REQUEST)
  transactions=StockTransaction.objects.filter(finished_product=product).filter(
   models.Q(destination_location=location)|models.Q(source_location=location)
  )
  totals=transactions.aggregate(
   quantity=Sum(F("quantity_in")-F("quantity_out"),default=Decimal("0")),
   value=Sum(Case(
    When(destination_location=location,then=F("total_value")),
    When(source_location=location,then=-F("total_value")),
    default=Value(Decimal("0")),output_field=DecimalField(max_digits=18,decimal_places=4),
   ),default=Decimal("0")),
  )
  quantity=totals["quantity"] or Decimal("0")
  if quantity<=0:
   return Response({"success":False,"message":"This inventory row has no available stock to remove."},status=status.HTTP_400_BAD_REQUEST)
  unit_cost=(totals["value"] or Decimal("0"))/quantity
  reference_id=uuid.uuid4()
  transaction=StockTransaction.objects.create(
   transaction_number=f"CLEAR-FG-{reference_id}",transaction_date=timezone.now(),
   transaction_type="STOCK_ADJUSTMENT_OUT",reference_type="ClearFinishedGoods",reference_id=reference_id,
   finished_product=product,batch="",source_location=location,quantity_out=quantity,
   unit=product.sales_unit,unit_cost=unit_cost,total_value=quantity*unit_cost,
   remarks=f"Inventory row removed: {reason}",created_by=request.user,
  )
  return Response({"success":True,"message":"Finished-goods inventory row removed.","data":self.get_serializer(transaction).data},status=status.HTTP_201_CREATED)
 @action(detail=False,methods=["post"],url_path="opening-raw-material")
 @idempotent_action
 def opening_raw_material(self,request):
  from apps.locations.models import Location
  from apps.master_data.models import RawMaterial
  try:
   material=RawMaterial.objects.get(pk=request.data.get("raw_material"),status="ACTIVE")
   location=Location.objects.get(pk=request.data.get("location"),location_type="RAW_MATERIAL_WAREHOUSE",is_active=True)
   quantity=Decimal(str(request.data.get("quantity",0)))
   unit_cost=Decimal(str(request.data.get("unit_cost",material.current_average_cost)))
   opening_date=opening_datetime(request.data.get("opening_date"))
   notes=str(request.data.get("notes","")).strip() or "Opening raw-material stock"
   if quantity<=0 or unit_cost<0: raise ValueError
  except (RawMaterial.DoesNotExist,Location.DoesNotExist,ValueError,TypeError):
   return Response({"success":False,"message":"A valid raw material, raw-material warehouse and positive quantity are required."},status=status.HTTP_400_BAD_REQUEST)
  if StockTransaction.objects.filter(reference_type="OpeningStock",raw_material=material,destination_location=location,is_reversal=False).exists():
   return Response({"success":False,"message":"Opening stock already exists for this material and location. Use a stock adjustment instead."},status=status.HTTP_400_BAD_REQUEST)
  reference_id=uuid.uuid4()
  from .posting import post_movement
  transaction,_=post_movement(item=material,location=location,quantity=quantity,direction="IN",transaction_number=f"OPEN-RM-{reference_id}",transaction_type="OPENING_STOCK",reference_type="OpeningStock",reference_id=reference_id,unit=material.base_unit,user=request.user,incoming_unit_cost=unit_cost,remarks=notes,audit_action="Opening stock",transaction_date=opening_date)
  return Response({"success":True,"message":"Opening raw-material stock added.","data":self.get_serializer(transaction).data},status=status.HTTP_201_CREATED)
