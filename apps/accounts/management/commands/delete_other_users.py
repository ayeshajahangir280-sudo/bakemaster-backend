from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Deletes every User except the one with the given email."

    def add_arguments(self, parser):
        parser.add_argument("--keep-user", required=True, help="Email of the user to keep.")
        parser.add_argument(
            "--yes", action="store_true",
            help="Skip the interactive confirmation prompt.",
        )

    def handle(self, *args, **options):
        keep_email = options["keep_user"]
        try:
            keep_user = User.objects.get(email=keep_email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email {keep_email!r}.")

        others = User.objects.exclude(pk=keep_user.pk)
        count = others.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No other users to delete."))
            return

        if not options["yes"]:
            self.stdout.write(f"Users to be deleted ({count}):")
            for u in others:
                self.stdout.write(f"  - {u.email} ({u.role})")
            confirm = input(f"Delete these {count} users, keeping only {keep_email!r}? Type 'DELETE USERS' to continue: ")
            if confirm != "DELETE USERS":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        with transaction.atomic():
            deleted, _ = others.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {deleted} user(s). Only {keep_email!r} remains."
        ))
