from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
import uuid
import unittest

from django.db import close_old_connections,connection
from django.test import TransactionTestCase,tag
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.inventory.models import InventoryBalance,StockTransaction
from apps.inventory.posting import post_movement
from apps.locations.models import Location
from apps.master_data.models import Customer,FinishedProduct,ItemCategory,PaymentMethod,RawMaterial,Supplier,UnitOfMeasurement
from apps.payments.models import CustomerPayment,CustomerPaymentAllocation,SupplierPayment,SupplierPaymentAllocation
from apps.payments.services import cancel_payment,post_payment
from apps.purchasing.models import PurchaseInvoice,SupplierLedger
from apps.sales.models import CustomerLedger,SalesInvoice,SalesInvoiceItem,SalesReturn,SalesReturnItem
from apps.sales.services import post_return,post_sale
from apps.inventory.models import StockAdjustment,WastageDocument
from apps.inventory.document_services import generated_number,post_stock_document
from apps.transfers.models import FinishedGoodsTransfer,FinishedGoodsTransferItem,MaterialTransfer,MaterialTransferItem
from apps.transfers.services import dispatch,receive
from apps.transfers.services import cancel_transfer
from apps.recipes.models import Recipe,RecipeItem
from apps.production.models import ProductionBatch
from apps.production.services import complete_production
from apps.system_state.models import ERPState


@tag("postgres")
class PostgreSQLLockingTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor!="postgresql":raise unittest.SkipTest("PostgreSQL-only locking tests")
    def setUp(self):
        self.user=User.objects.create_user("pg@test.local","password",full_name="PG",employee_code="PG",role="ADMINISTRATOR")
        self.unit=UnitOfMeasurement.objects.create(code="PG-U",name="Unit")
        category=ItemCategory.objects.create(name="PG-FG",kind="FG")
        rm_category=ItemCategory.objects.create(name="PG-RM",kind="RM")
        self.product=FinishedProduct.objects.create(product_code="PG-FG",name="Product",category=category,sales_unit=self.unit)
        self.location=Location.objects.create(code="PG-L",name="Shop",location_type="SHOP")
        self.customer=Customer.objects.create(customer_code="PG-C",name="Customer",assigned_location=self.location)
        self.method=PaymentMethod.objects.create(name="PG Bank")
        self.raw=RawMaterial.objects.create(material_code="PG-RM",name="Flour",category=rm_category,base_unit=self.unit,purchase_unit=self.unit,consumption_unit=self.unit)
        self.production_location=Location.objects.create(code="PG-PROD",name="Production",location_type="PRODUCTION")
        self.destination=Location.objects.create(code="PG-DEST",name="Destination",location_type="FINISHED_GOODS_WAREHOUSE")
        self.supplier=Supplier.objects.create(supplier_code="PG-S",name="Supplier")
        self.recipe=Recipe.objects.create(recipe_number="PG-R",finished_product=self.product,standard_output_quantity=1,output_unit=self.unit,version="1",effective_date=timezone.localdate(),status="ACTIVE")
        RecipeItem.objects.create(recipe=self.recipe,raw_material=self.raw,required_quantity=4,unit=self.unit)
    def concurrently(self,*operations):
        barrier=Barrier(len(operations))
        def invoke(operation):
            close_old_connections();barrier.wait()
            try:operation();return "ok"
            except Exception as exc:return f"{exc.__class__.__name__}: {exc}"
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:return list(pool.map(invoke,operations))
    def add_stock(self,quantity):
        post_movement(item=self.product,location=self.location,quantity=quantity,direction="IN",transaction_number=f"PG-IN-{uuid.uuid4()}",transaction_type="PRODUCTION_OUTPUT",reference_type="Test",reference_id=uuid.uuid4(),unit=self.unit,user=self.user,incoming_unit_cost=Decimal("2"))
    def add_raw(self,quantity):post_movement(item=self.raw,location=self.location,quantity=quantity,direction="IN",transaction_number=f"PG-RM-IN-{uuid.uuid4()}",transaction_type="PURCHASE",reference_type="Test",reference_id=uuid.uuid4(),unit=self.unit,user=self.user,incoming_unit_cost=Decimal("3"))
    def material_transfer(self,number,quantity):
        obj=MaterialTransfer.objects.create(transfer_number=number,transfer_date=timezone.localdate(),source_location=self.location,destination_location=self.production_location,status="APPROVED",requested_by=self.user);MaterialTransferItem.objects.create(transfer=obj,raw_material=self.raw,quantity=quantity,unit=self.unit);return obj
    def finished_transfer(self,number,quantity):
        obj=FinishedGoodsTransfer.objects.create(transfer_number=number,transfer_date=timezone.localdate(),source_location=self.location,destination_location=self.destination,status="APPROVED");FinishedGoodsTransferItem.objects.create(transfer=obj,finished_product=self.product,requested_quantity=quantity,unit=self.unit);return obj
    def wastage(self,number,item,quantity,location=None):return WastageDocument.objects.create(document_number=number,wastage_date=timezone.localdate(),raw_material=item if isinstance(item,RawMaterial) else None,finished_product=item if isinstance(item,FinishedProduct) else None,location=location or self.location,quantity=quantity,unit=self.unit,reason="race",status="APPROVED")
    def adjustment(self,number,item,quantity):return StockAdjustment.objects.create(adjustment_number=number,adjustment_date=timezone.localdate(),raw_material=item if isinstance(item,RawMaterial) else None,finished_product=item if isinstance(item,FinishedProduct) else None,location=self.location,quantity=quantity,unit=self.unit,reason="race",direction="NEGATIVE",status="APPROVED")
    def invoice(self,number,quantity):
        invoice=SalesInvoice.objects.create(invoice_number=number,customer=self.customer,invoice_date=timezone.localdate(),sales_location=self.location,status="DRAFT")
        SalesInvoiceItem.objects.create(sales_invoice=invoice,finished_product=self.product,quantity=quantity,unit=self.unit,selling_price=Decimal("10"))
        return invoice
    def test_two_sales_cannot_oversell(self):
        self.add_stock(Decimal("5"));first=self.invoice("PG-S1",Decimal("4"));second=self.invoice("PG-S2",Decimal("4"))
        results=self.concurrently(lambda:post_sale(first.pk,self.user),lambda:post_sale(second.pk,self.user))
        balance=InventoryBalance.objects.get(finished_product=self.product,location=self.location)
        self.assertEqual(results.count("ok"),1);self.assertEqual(balance.current_quantity,Decimal("1"));self.assertGreaterEqual(balance.inventory_value,0);self.assertEqual(StockTransaction.objects.filter(transaction_type="SALE").count(),1)
    def test_concurrent_missing_balance_creation_has_one_row_and_no_lost_update(self):
        def incoming():post_movement(item=self.product,location=self.location,quantity=1,direction="IN",transaction_number=f"PG-CREATE-{uuid.uuid4()}",transaction_type="PRODUCTION_OUTPUT",reference_type="Test",reference_id=uuid.uuid4(),unit=self.unit,user=self.user,incoming_unit_cost=Decimal("2"))
        results=self.concurrently(incoming,incoming);balance=InventoryBalance.objects.get(finished_product=self.product,location=self.location)
        self.assertEqual(results,["ok","ok"]);self.assertEqual(InventoryBalance.objects.count(),1);self.assertEqual(balance.current_quantity,Decimal("2"));self.assertEqual(balance.average_unit_cost,Decimal("2"))
    def payment(self,number,invoice,amount):
        payment=CustomerPayment.objects.create(payment_number=number,customer=self.customer,payment_date=timezone.localdate(),amount=amount,payment_method=self.method)
        CustomerPaymentAllocation.objects.create(payment=payment,invoice=invoice,amount=amount);return payment
    def test_concurrent_payments_cannot_overallocate(self):
        invoice=self.invoice("PG-PAY-I",Decimal("1"));invoice.status="POSTED";invoice.grand_total=Decimal("100");invoice.outstanding_amount=Decimal("100");invoice.save()
        first=self.payment("PG-P1",invoice,Decimal("80"));second=self.payment("PG-P2",invoice,Decimal("80"))
        results=self.concurrently(lambda:post_payment(CustomerPayment,first.pk,self.user),lambda:post_payment(CustomerPayment,second.pk,self.user));invoice.refresh_from_db()
        self.assertEqual(results.count("ok"),1);self.assertEqual(invoice.outstanding_amount,Decimal("20"));self.assertEqual(CustomerLedger.objects.count(),1)
    def test_duplicate_post_and_cancel_have_single_financial_effect(self):
        invoice=self.invoice("PG-IDEM-I",Decimal("1"));invoice.status="POSTED";invoice.grand_total=Decimal("50");invoice.outstanding_amount=Decimal("50");invoice.save()
        payment=self.payment("PG-IDEM",invoice,Decimal("50"))
        self.assertEqual(self.concurrently(lambda:post_payment(CustomerPayment,payment.pk,self.user),lambda:post_payment(CustomerPayment,payment.pk,self.user)),["ok","ok"])
        self.assertEqual(CustomerLedger.objects.count(),1)
        self.assertEqual(self.concurrently(lambda:cancel_payment(CustomerPayment,payment.pk,self.user,"retry"),lambda:cancel_payment(CustomerPayment,payment.pk,self.user,"retry")),["ok","ok"])
        self.assertEqual(CustomerLedger.objects.count(),2);invoice.refresh_from_db();self.assertEqual(invoice.outstanding_amount,Decimal("50"))
    def test_two_material_transfers_cannot_overdispatch(self):
        self.add_raw(5);a=self.material_transfer("PG-MT-A",4);b=self.material_transfer("PG-MT-B",4);results=self.concurrently(lambda:dispatch(a,self.user),lambda:dispatch(b,self.user));balance=InventoryBalance.objects.get(raw_material=self.raw,location=self.location);self.assertEqual(results.count("ok"),1);self.assertEqual(balance.current_quantity,1)
    def test_two_finished_transfers_cannot_overdispatch(self):
        self.add_stock(5);a=self.finished_transfer("PG-FT-A",4);b=self.finished_transfer("PG-FT-B",4);results=self.concurrently(lambda:dispatch(a,self.user,True),lambda:dispatch(b,self.user,True));self.assertEqual(results.count("ok"),1);self.assertEqual(InventoryBalance.objects.get(finished_product=self.product,location=self.location).current_quantity,1)
    def test_duplicate_transfer_dispatch_has_one_movement(self):
        self.add_raw(5);obj=self.material_transfer("PG-MT-DUP",4);results=self.concurrently(lambda:dispatch(obj,self.user),lambda:dispatch(obj,self.user));self.assertEqual(results.count("ok"),1);self.assertEqual(StockTransaction.objects.filter(reference_type="MaterialTransfer",reference_id=obj.id,transaction_type="RAW_MATERIAL_TRANSFER_OUT").count(),1)
    def test_competing_receipts_cannot_overreceive(self):
        self.add_stock(5);obj=self.finished_transfer("PG-FT-REC",5);dispatch(obj,self.user,True);line=obj.items.get();payload=[{"id":str(line.id),"received_quantity":"5","damaged_quantity":"0"}];results=self.concurrently(lambda:receive(obj,self.user,payload,True),lambda:receive(obj,self.user,payload,True));self.assertEqual(results.count("ok"),1);line.refresh_from_db();self.assertEqual(line.received_quantity,5)
    def test_wastage_documents_compete_for_balance(self):
        self.add_stock(5);a=self.wastage("PG-W-A",self.product,4);b=self.wastage("PG-W-B",self.product,4);results=self.concurrently(lambda:post_stock_document(WastageDocument,a.id,self.user),lambda:post_stock_document(WastageDocument,b.id,self.user));self.assertEqual(results.count("ok"),1);self.assertEqual(InventoryBalance.objects.get(finished_product=self.product,location=self.location).current_quantity,1)
    def test_negative_adjustments_compete_for_balance(self):
        self.add_stock(5);a=self.adjustment("PG-A-A",self.product,4);b=self.adjustment("PG-A-B",self.product,4);results=self.concurrently(lambda:post_stock_document(StockAdjustment,a.id,self.user),lambda:post_stock_document(StockAdjustment,b.id,self.user));self.assertEqual(results.count("ok"),1);self.assertEqual(InventoryBalance.objects.get(finished_product=self.product,location=self.location).current_quantity,1)
    def test_sale_and_wastage_compete(self):
        self.add_stock(5);invoice=self.invoice("PG-SW",4);waste=self.wastage("PG-SW-W",self.product,4);results=self.concurrently(lambda:post_sale(invoice.id,self.user),lambda:post_stock_document(WastageDocument,waste.id,self.user));self.assertEqual(results.count("ok"),1);self.assertGreaterEqual(InventoryBalance.objects.get(finished_product=self.product,location=self.location).current_quantity,0)
    def test_duplicate_wastage_and_adjustment_post_once(self):
        self.add_stock(10);waste=self.wastage("PG-W-DUP",self.product,2);adjust=self.adjustment("PG-A-DUP",self.product,2);self.concurrently(lambda:post_stock_document(WastageDocument,waste.id,self.user),lambda:post_stock_document(WastageDocument,waste.id,self.user));self.concurrently(lambda:post_stock_document(StockAdjustment,adjust.id,self.user),lambda:post_stock_document(StockAdjustment,adjust.id,self.user));self.assertEqual(StockTransaction.objects.filter(reference_type="WastageDocument",reference_id=waste.id).count(),1);self.assertEqual(StockTransaction.objects.filter(reference_type="StockAdjustment",reference_id=adjust.id).count(),1)
    def test_concurrent_supplier_payments_cannot_overallocate(self):
        invoice=PurchaseInvoice.objects.create(invoice_number="PG-PI",supplier=self.supplier,invoice_date=timezone.localdate(),warehouse=self.location,status="POSTED",grand_total=100,outstanding_amount=100)
        def payment(number):
            obj=SupplierPayment.objects.create(payment_number=number,supplier=self.supplier,payment_date=timezone.localdate(),amount=80,payment_method=self.method);SupplierPaymentAllocation.objects.create(payment=obj,invoice=invoice,amount=80);return obj
        a=payment("PG-SP-A");b=payment("PG-SP-B");results=self.concurrently(lambda:post_payment(SupplierPayment,a.id,self.user),lambda:post_payment(SupplierPayment,b.id,self.user));invoice.refresh_from_db();self.assertEqual(results.count("ok"),1);self.assertEqual(invoice.outstanding_amount,20);self.assertEqual(SupplierLedger.objects.count(),1)
    def test_concurrent_document_numbers_are_unique(self):
        with ThreadPoolExecutor(max_workers=8) as pool:numbers=list(pool.map(lambda _:generated_number("PG"),range(100)))
        self.assertEqual(len(numbers),len(set(numbers)))
    def test_two_returns_cannot_overreturn_original_line(self):
        invoice=self.invoice("PG-RET-I",5);invoice.status="POSTED";invoice.grand_total=50;invoice.outstanding_amount=50;invoice.save();line=invoice.items.get();line.line_total=50;line.unit_cost_snapshot=2;line.save()
        def make(number):
            ret=SalesReturn.objects.create(return_number=number,customer=self.customer,original_sales_invoice=invoice,return_date=timezone.localdate(),return_location=self.location,reason="race");SalesReturnItem.objects.create(sales_return=ret,original_sales_invoice_item=line,finished_product=self.product,sold_quantity=5,return_quantity=4,condition="SALEABLE",unit_price=10,credit_amount=40);return ret
        a=make("PG-RET-A");b=make("PG-RET-B");results=self.concurrently(lambda:post_return(a.id,self.user),lambda:post_return(b.id,self.user));self.assertEqual(results.count("ok"),1,results);self.assertEqual(SalesReturn.objects.filter(status="POSTED").count(),1)
    def test_production_and_transfer_compete_for_raw_material(self):
        post_movement(item=self.raw,location=self.production_location,quantity=5,direction="IN",transaction_number="PG-PROD-RM",transaction_type="PURCHASE",reference_type="Test",reference_id=uuid.uuid4(),unit=self.unit,user=self.user,incoming_unit_cost=3)
        production=ProductionBatch.objects.create(production_number="PG-PROD",finished_product=self.product,recipe=self.recipe,planned_quantity=1,production_location=self.production_location,finished_goods_destination=self.destination,batch_number="PG",manufacturing_date=timezone.localdate())
        transfer=MaterialTransfer.objects.create(transfer_number="PG-PROD-MT",transfer_date=timezone.localdate(),source_location=self.production_location,destination_location=self.destination,status="APPROVED",requested_by=self.user);MaterialTransferItem.objects.create(transfer=transfer,raw_material=self.raw,quantity=4,unit=self.unit)
        results=self.concurrently(lambda:complete_production(production.id,self.user),lambda:dispatch(transfer,self.user));self.assertEqual(results.count("ok"),1);self.assertGreaterEqual(InventoryBalance.objects.get(raw_material=self.raw,location=self.production_location).current_quantity,0)
    def test_concurrent_transfer_cancellation_has_single_reversal_set(self):
        self.add_raw(5);obj=self.material_transfer("PG-CANCEL-MT",4);dispatch(obj,self.user);results=self.concurrently(lambda:cancel_transfer(obj,self.user,"race"),lambda:cancel_transfer(obj,self.user,"race"));self.assertEqual(results,["ok","ok"]);originals=StockTransaction.objects.filter(reference_type="MaterialTransfer",reference_id=obj.id,is_reversal=False);self.assertEqual(StockTransaction.objects.filter(reversal_of__in=originals).count(),originals.count())
    def test_stale_erpstate_write_cannot_change_normalized_stock(self):
        self.add_stock(1)
        def stale():ERPState.objects.update_or_create(key="default",defaults={"data":{"uiPreferences":{"theme":"dark"}},"updated_by":self.user})
        results=self.concurrently(lambda:post_movement(item=self.product,location=self.location,quantity=1,direction="IN",transaction_number="PG-STATE-IN",transaction_type="PRODUCTION_OUTPUT",reference_type="Test",reference_id=uuid.uuid4(),unit=self.unit,user=self.user,incoming_unit_cost=2),stale);self.assertEqual(results,["ok","ok"]);self.assertEqual(InventoryBalance.objects.get(finished_product=self.product,location=self.location).current_quantity,2)
