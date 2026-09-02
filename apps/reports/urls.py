from django.urls import path
from .views import DashboardView,DocumentReport,InventoryReport,ProductionReport,PurchaseReport,ReconciliationReport,ReportExportCollectionView,ReportExportDetailView,ReportExportDownloadView,ReturnsPaymentsReport,SalesReport,StockLedgerReport

urlpatterns=[path("dashboard/",DashboardView.as_view(),name="dashboard")]
urlpatterns += [path("report-exports/",ReportExportCollectionView.as_view(),name="report-export-list"),path("report-exports/<uuid:pk>/",ReportExportDetailView.as_view(),name="report-export-detail"),path("report-exports/<uuid:pk>/download/",ReportExportDownloadView.as_view(),name="report-export-download")]
def add(slugs,view):
    for slug in slugs:urlpatterns.append(path(f"reports/{slug}/",view.as_view(report_name=slug),name=f"report-{slug}"))
add(("raw-material-stock","production-stock","finished-goods-stock","stock-by-location","inventory-valuation"),InventoryReport)
urlpatterns.append(path("reports/stock-ledger/",StockLedgerReport.as_view(),name="report-stock-ledger"))
add(("stock-movement","item-movement-history"),StockLedgerReport)
add(("wastage","adjustments"),DocumentReport)
add(("purchase-register","supplier-ledger","supplier-outstanding","purchases-by-item"),PurchaseReport)
add(("production-register","material-consumption","production-cost","production-efficiency"),ProductionReport)
add(("sales-register","customer-ledger","customer-outstanding","sales-by-product","sales-by-customer","sales-by-branch","daily-sales","monthly-sales","gross-profit"),SalesReport)
add(("sales-returns","return-analysis","customer-return-history","customer-payments","supplier-payments"),ReturnsPaymentsReport)
urlpatterns.append(path("reports/reconciliation/",ReconciliationReport.as_view(),name="report-reconciliation"))
