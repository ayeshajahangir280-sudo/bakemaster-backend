import hashlib
import json
from datetime import timedelta
from functools import wraps

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.response import Response

from apps.system_state.models import IdempotencyRecord


def _request_hash(request):
    encoded = json.dumps(request.data, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def idempotent_action(view_method):
    """Persist and replay successful authoritative actions for 24 hours."""
    @wraps(view_method)
    def wrapped(view, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key:
            return view_method(view, request, *args, **kwargs)
        if len(key) > 200:
            return Response({"detail": "Idempotency-Key must be 200 characters or fewer."}, status=400)
        action = f"{request.method}:{request.path}"
        digest = _request_hash(request)
        now = timezone.now()
        try:
            with transaction.atomic():
                record, created = IdempotencyRecord.objects.select_for_update().get_or_create(
                    user=request.user,
                    key=key,
                    action=action,
                    defaults={"request_hash": digest, "expires_at": now + timedelta(hours=24)},
                )
                if not created:
                    if record.request_hash != digest:
                        return Response({"detail": "Idempotency-Key was already used with a different payload."}, status=409)
                    if record.state == "COMPLETED":
                        response = Response(record.response_body, status=record.response_status)
                        response["Idempotency-Replayed"] = "true"
                        return response
                    return Response({"detail": "An identical request is already being processed."}, status=409)
                response = view_method(view, request, *args, **kwargs)
                if response.status_code < 500:
                    record.state = "COMPLETED"
                    record.response_status = response.status_code
                    record.response_body = json.loads(json.dumps(response.data, default=str))
                    record.completed_at = timezone.now()
                    record.save(update_fields=["state", "response_status", "response_body", "completed_at"])
                else:
                    record.delete()
                return response
        except IntegrityError:
            return Response({"detail": "An identical request is already being processed."}, status=409)
    return wrapped
