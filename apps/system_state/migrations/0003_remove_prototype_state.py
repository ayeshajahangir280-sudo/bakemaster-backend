from django.db import migrations

def remove_prototype_state(apps,schema_editor):
    ERPState=apps.get_model("system_state","ERPState")
    for state in ERPState.objects.all().iterator():
        data=state.data if isinstance(state.data,dict) else {}
        safe={"uiPreferences":data["uiPreferences"]} if "uiPreferences" in data else {}
        if safe!=data:
            state.data=safe;state.revision+=1;state.save(update_fields=["data","revision","updated_at"])

class Migration(migrations.Migration):
    dependencies=[("system_state","0002_remove_transactional_snapshot_data")]
    operations=[migrations.RunPython(remove_prototype_state,migrations.RunPython.noop)]
