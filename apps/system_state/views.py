from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiTypes,extend_schema,inline_serializer
from rest_framework import serializers

from .models import ERPState

ERP_STATE_ALLOWED_KEYS=frozenset({"uiPreferences"})
ERP_STATE_TRANSACTIONAL_KEYS=frozenset({
    "purchaseInvoices","productionBatches","openingStocks","stockAdjustments","wastages","materialTransfers","stockTransfers",
    "salesInvoices","salesReturns","customerPayments","supplierPayments","stockLedger","inventoryBalances","customerBalances",
    "supplierBalances","reports","dashboard","counters",
})
ERP_STATE_FORBIDDEN_NORMALIZED={"".join(ch for ch in key.lower() if ch.isalnum()) for key in ERP_STATE_TRANSACTIONAL_KEYS}|{"stock","ledger","invoice","payment","purchase","production","transfer","return","wastage","adjustment","balance","report","dashboard"}

def validate_ui_preferences(value,path="uiPreferences"):
    if isinstance(value,list):return f"{path} cannot contain arrays."
    if isinstance(value,dict):
        for key,nested in value.items():
            normalized="".join(ch for ch in str(key).lower() if ch.isalnum())
            if any(token in normalized for token in ERP_STATE_FORBIDDEN_NORMALIZED):return f"{path}.{key} resembles transactional data and is not allowed."
            error=validate_ui_preferences(nested,f"{path}.{key}")
            if error:return error
        return None
    if value is None or isinstance(value,(str,int,float,bool)):return None
    return f"{path} contains an unsupported value."

class ERPStateView(APIView):
    @extend_schema(operation_id="erp_state_retrieve",responses=OpenApiTypes.OBJECT)
    def get(self, request):
        state = ERPState.objects.filter(key="default").first()
        if state is None:
            return Response({"data": None, "revision": 0})
        safe_data={key:state.data[key] for key in ERP_STATE_ALLOWED_KEYS if key in state.data}
        return Response({"data": safe_data, "revision": state.revision})

    @transaction.atomic
    @extend_schema(operation_id="erp_state_update",request=inline_serializer("ERPStateUpdateRequest",fields={"data":serializers.JSONField(),"revision":serializers.IntegerField()}),responses=OpenApiTypes.OBJECT)
    def put(self, request):
        data = request.data.get("data")
        expected_revision = request.data.get("revision")
        if not isinstance(data, dict):
            return Response({"detail": "data must be a JSON object"}, status=400)
        if expected_revision is None:
            return Response({"detail": "revision is required for optimistic locking"}, status=400)
        rejected=sorted(set(data)-ERP_STATE_ALLOWED_KEYS)
        if rejected:
            return Response({"detail":"ERPState only accepts prototype/UI snapshot data. Normalized transactional data must use its backend API.","rejected_keys":rejected,"allowed_keys":sorted(ERP_STATE_ALLOWED_KEYS)},status=400)
        if "uiPreferences" in data:
            error=validate_ui_preferences(data["uiPreferences"])
            if error:return Response({"detail":error},status=400)

        state, created = ERPState.objects.select_for_update().get_or_create(key="default")
        if created:
            state.revision = 0
        if int(expected_revision) != state.revision:
            return Response({"detail": "ERP state is stale. Refresh before saving.", "revision": state.revision}, status=409)
        state.data = {key:data[key] for key in ERP_STATE_ALLOWED_KEYS if key in data}
        state.revision += 1
        state.updated_by = request.user
        state.save(update_fields=["data", "revision", "updated_by", "updated_at"])
        return Response({"revision": state.revision, "updated_at": state.updated_at})
