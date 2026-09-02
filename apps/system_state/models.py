from django.conf import settings
from django.db import models


class ERPState(models.Model):
    key = models.CharField(max_length=40, unique=True, default="default")
    data = models.JSONField(default=dict)
    revision = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="erp_state_updates",
    )


class IdempotencyRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=200)
    action = models.CharField(max_length=300)
    request_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=12, default="PROCESSING")
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key", "action"], name="unique_idempotency_user_key_action"
            )
        ]
        indexes = [models.Index(fields=["expires_at"], name="idempotency_expiry_idx")]
