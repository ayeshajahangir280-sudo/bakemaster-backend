import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import User
from apps.inventory.models import InventoryBalance,StockTransaction
from apps.locations.models import Location
from apps.master_data.models import Customer,FinishedProduct,ItemCategory,RawMaterial,Supplier,UnitOfMeasurement
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice,SalesInvoiceItem

class Command(BaseCommand):
 help="Generate synthetic, non-production query-plan fixtures."
 def add_arguments(self,p):
  for name,default in (("products",100),("materials",100),("customers",500),("suppliers",100),("locations",10),("sales",5000),("purchases",2000),("ledger_entries",20000)):p.add_argument(f"--{name.replace('_','-')}",type=int,default=default)
 def handle(self,*args,**o):
  user,_=User.objects.get_or_create(email="plans@bakeryflow.test",defaults={"full_name":"Plan Fixture","employee_code":"PLAN","role":"ADMINISTRATOR"});unit,_=UnitOfMeasurement.objects.get_or_create(code="PLAN-U",defaults={"name":"Unit"});fgc,_=ItemCategory.objects.get_or_create(name="Plan FG",kind="FG");rmc,_=ItemCategory.objects.get_or_create(name="Plan RM",kind="RM")
  locations=[Location(code=f"PLAN-L{i}",name=f"Plan Location {i}",location_type="SHOP") for i in range(o["locations"])];Location.objects.bulk_create(locations,ignore_conflicts=True);locations=list(Location.objects.filter(code__startswith="PLAN-L"))
  RawMaterial.objects.bulk_create([RawMaterial(material_code=f"PLAN-RM-{i}",name=f"Material {i}",category=rmc,base_unit=unit,purchase_unit=unit,consumption_unit=unit) for i in range(o["materials"])],ignore_conflicts=True);materials=list(RawMaterial.objects.filter(material_code__startswith="PLAN-RM-"))
  FinishedProduct.objects.bulk_create([FinishedProduct(product_code=f"PLAN-FG-{i}",name=f"Product {i}",category=fgc,sales_unit=unit) for i in range(o["products"])],ignore_conflicts=True);products=list(FinishedProduct.objects.filter(product_code__startswith="PLAN-FG-"))
  Customer.objects.bulk_create([Customer(customer_code=f"PLAN-C-{i}",name=f"Customer {i}") for i in range(o["customers"])],ignore_conflicts=True);customers=list(Customer.objects.filter(customer_code__startswith="PLAN-C-"));Supplier.objects.bulk_create([Supplier(supplier_code=f"PLAN-S-{i}",name=f"Supplier {i}") for i in range(o["suppliers"])],ignore_conflicts=True);suppliers=list(Supplier.objects.filter(supplier_code__startswith="PLAN-S-"))
  today=timezone.localdate();SalesInvoice.objects.bulk_create([SalesInvoice(invoice_number=f"PLAN-SI-{i}",customer=customers[i%len(customers)],invoice_date=today,sales_location=locations[i%len(locations)],status="POSTED",grand_total=10,outstanding_amount=5,gross_profit=3) for i in range(o["sales"])],ignore_conflicts=True);sales=list(SalesInvoice.objects.filter(invoice_number__startswith="PLAN-SI-"));SalesInvoiceItem.objects.bulk_create([SalesInvoiceItem(sales_invoice=s,finished_product=products[i%len(products)],quantity=1,unit=unit,selling_price=10,line_total=10,cost_total=7,gross_profit=3) for i,s in enumerate(sales)],ignore_conflicts=True)
  PurchaseInvoice.objects.bulk_create([PurchaseInvoice(invoice_number=f"PLAN-PI-{i}",supplier=suppliers[i%len(suppliers)],invoice_date=today,warehouse=locations[i%len(locations)],status="POSTED",grand_total=8,outstanding_amount=4) for i in range(o["purchases"])],ignore_conflicts=True)
  entries=[];pair_counts={}
  for i in range(o["ledger_entries"]):
   p=products[i%len(products)];l=locations[i%len(locations)];pair_counts[(p.id,l.id)]=pair_counts.get((p.id,l.id),0)+1;entries.append(StockTransaction(transaction_number=f"PLAN-ST-{i}",transaction_date=timezone.now(),transaction_type="PRODUCTION_OUTPUT",reference_type="PlanFixture",reference_id=uuid.uuid4(),finished_product=p,destination_location=l,quantity_in=1,unit=unit,unit_cost=7,total_value=7,created_by=user))
  StockTransaction.objects.bulk_create(entries,ignore_conflicts=True,batch_size=1000);InventoryBalance.objects.bulk_create([InventoryBalance(finished_product_id=p,location_id=l,current_quantity=q,inventory_value=q*7,average_unit_cost=7) for (p,l),q in pair_counts.items()],ignore_conflicts=True);self.stdout.write(self.style.SUCCESS(f"Seeded {len(sales)} sales and {len(entries)} ledger entries"))
