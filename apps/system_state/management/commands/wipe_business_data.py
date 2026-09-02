from django.core.management.base import BaseCommand
from django.db import transaction
from django.apps import apps

from common.viewsets import hard_delete_instance
from apps.system_state.models import ERPState

APP_LABELS = {
    "master_data", "inventory", "purchasing", "recipes",
    "production", "transfers", "sales", "payments", "audit", "reports",
    "system_state",
}


class Command(BaseCommand):
    help = "Deletes all ERP business/transactional data, preserving Users and Locations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true",
            help="Skip the interactive confirmation prompt.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            confirm = input(
                "This will permanently delete ALL business data (inventory, purchasing, "
                "sales, production, recipes, transfers, payments, audit, reports) from "
                "every location. Users and Locations are kept. Type 'DELETE ALL DATA' to continue: "
            )
            if confirm != "DELETE ALL DATA":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        with transaction.atomic():
            seen = set()
            for model in apps.get_models():
                if model._meta.app_label not in APP_LABELS:
                    continue
                if model is ERPState:
                    continue
                for instance in list(model._base_manager.all()):
                    hard_delete_instance(instance, seen)
            ERPState.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(
            "All business data deleted. Users and Locations were preserved."
        ))
