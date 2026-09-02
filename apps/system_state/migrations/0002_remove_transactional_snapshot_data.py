from django.db import migrations

ALLOWED_KEYS={"uiPreferences","prototypeData"}

def keep_only_allowed_state(apps,schema_editor):
    ERPState=apps.get_model("system_state","ERPState")
    for state in ERPState.objects.all().iterator():
        existing=state.data if isinstance(state.data,dict) else {}
        safe={key:existing[key] for key in ALLOWED_KEYS if key in existing}
        if safe!=existing:
            state.data=safe
            state.revision+=1
            state.save(update_fields=["data","revision","updated_at"])

class Migration(migrations.Migration):
    dependencies=[("system_state","0001_initial")]
    operations=[migrations.RunPython(keep_only_allowed_state,migrations.RunPython.noop)]
