import io
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.accounts.models import User


class TestAccountStartupTests(TestCase):
    env_keys = {
        "CREATE_TEST_ACCOUNT": "false",
        "TEST_ACCOUNT_EMAIL": "test@bakemastererp.com",
        "TEST_ACCOUNT_PASSWORD": "",
    }

    def test_test_account_creation_is_disabled_by_default(self):
        output = io.StringIO()
        with patch.dict("os.environ", self.env_keys, clear=False):
            call_command("ensure_test_account", stdout=output)

        self.assertFalse(User.objects.filter(email="test@bakemastererp.com").exists())
        self.assertIn("disabled", output.getvalue().lower())

    def test_explicit_opt_in_creates_account_without_logging_password(self):
        output = io.StringIO()
        password = "temporary-secret-password"
        environment = {
            **self.env_keys,
            "CREATE_TEST_ACCOUNT": "true",
            "TEST_ACCOUNT_PASSWORD": password,
        }
        with patch.dict("os.environ", environment, clear=False):
            call_command("ensure_test_account", stdout=output)

        user = User.objects.get(email="test@bakemastererp.com")
        self.assertTrue(user.check_password(password))
        self.assertNotIn(password, output.getvalue())

    def test_opt_in_requires_an_explicit_password(self):
        environment = {**self.env_keys, "CREATE_TEST_ACCOUNT": "true"}
        with patch.dict("os.environ", environment, clear=False):
            with self.assertRaises(CommandError):
                call_command("ensure_test_account")
        self.assertFalse(User.objects.filter(email="test@bakemastererp.com").exists())
