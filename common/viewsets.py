from rest_framework.viewsets import ModelViewSet
from django.db.models.deletion import ProtectedError, RestrictedError


def hard_delete_instance(instance, seen=None):
    """Recursively delete one explicitly authorized reset target."""
    seen = seen or set()
    identity = (instance._meta.label_lower, instance.pk)
    if identity in seen:
        return
    seen.add(identity)
    for relation in instance._meta.related_objects:
        if relation.many_to_many:
            continue
        field = relation.field
        related = relation.related_model._base_manager.filter(**{field.name: instance})
        if field.remote_field.on_delete.__name__ in {"SET_NULL", "SET_DEFAULT"}:
            related.update(**{field.name: None if field.null else field.get_default()})
        else:
            for child in list(related):
                hard_delete_instance(child, seen)
    instance.__class__._base_manager.filter(pk=instance.pk)._raw_delete(instance._state.db)


class AuditedModelViewSet(ModelViewSet):
    def perform_create(self,serializer): serializer.save(created_by=self.request.user,updated_by=self.request.user)
    def perform_update(self,serializer): serializer.save(updated_by=self.request.user)
    def perform_destroy(self,instance):
        try:
            instance.delete()
        except (ProtectedError,RestrictedError):
            # Preserve foreign-key history without blocking the user's delete.
            # Archived rows remain available to existing related records, while
            # API clients treat them as removed from active lists.
            fields={field.name for field in instance._meta.fields}
            if "is_active" in fields:
                instance.is_active=False
                update_fields=["is_active"]
            elif "status" in fields:
                instance.status="INACTIVE"
                update_fields=["status"]
            else:
                raise
            if "updated_by" in fields:
                instance.updated_by=self.request.user
                update_fields.append("updated_by")
            if "updated_at" in fields:
                update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
