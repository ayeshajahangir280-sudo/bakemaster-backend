import os
from django.core.management.base import BaseCommand
from apps.accounts.models import User
from apps.locations.models import Location
ROLE_MODULES={
 "PURCHASE":["dashboard","purchasing","suppliers","raw_materials","reports"],"PRODUCTION":["dashboard","material_transfers","recipes","production","wastage","finished_goods","reports"],"WAREHOUSE":["dashboard","raw_materials","inventory","stock_adjustments","material_transfers","finished_goods","stock_transfers","reports"],"SALES":["dashboard","stock_transfers","sales","customers","customer_payments","sales_returns","reports"],"ACCOUNTS":["dashboard","purchasing","suppliers","supplier_payments","customers","customer_payments","reports"],"MANAGER":[x[0] for x in User.MODULES if x[0] not in ("users","settings")],"ADMINISTRATOR":[x[0] for x in User.MODULES]}
class Command(BaseCommand):
 help="Seed locations and module-assigned demo users"
 def handle(self,*args,**opts):
  password=os.getenv("DEMO_PASSWORD","BakeryFlow2026!")
  locations={}
  specs=[("RMW","Raw Material Warehouse","RAW_MATERIAL_WAREHOUSE"),("PROD","Production Department","PRODUCTION"),("FGW","Finished Goods Warehouse","FINISHED_GOODS_WAREHOUSE"),("SHOP1","Shop 1","SHOP"),("SHOP2","Shop 2","SHOP"),("DMG","Damaged Goods Location","DAMAGED_GOODS"),("TRANSIT","In-Transit Location","IN_TRANSIT")]
  for code,name,kind in specs:locations[code],_=Location.objects.get_or_create(code=code,defaults={"name":name,"location_type":kind,"is_sales_location":kind=="SHOP","is_production_location":kind=="PRODUCTION"})
  users=[("admin","Administrator","ADMINISTRATOR",None,True),("purchase","Purchase User","PURCHASE","RMW",False),("production","Production User","PRODUCTION","PROD",False),("warehouse","Warehouse User","WAREHOUSE","FGW",False),("shop1","Shop 1 User","SALES","SHOP1",False),("shop2","Shop 2 User","SALES","SHOP2",False),("accounts","Accounts User","ACCOUNTS",None,True),("manager","Manager","MANAGER",None,True)]
  for key,name,role,loc,all_locs in users:
   u,created=User.objects.get_or_create(email=f"{key}@bakeryflow.local",defaults={"full_name":name,"employee_code":key.upper(),"role":role,"assigned_location":locations.get(loc),"can_access_all_locations":all_locs,"allowed_modules":ROLE_MODULES[role],"is_staff":role=="ADMINISTRATOR"})
   if created:u.set_password(password);u.save()
  self.stdout.write(self.style.SUCCESS("Demo data seeded."))
