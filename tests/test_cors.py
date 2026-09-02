from django.conf import settings
from django.test import SimpleTestCase, override_settings
from corsheaders.defaults import default_headers


@override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ORIGIN_ALLOW_ALL=False)
class CorsConfigurationTests(SimpleTestCase):
    frontend_origin = "https://bakemaster-erp.vercel.app"

    def test_standard_and_idempotency_headers_are_allowed(self):
        self.assertTrue(set(default_headers).issubset(set(settings.CORS_ALLOW_HEADERS)))
        self.assertIn("idempotency-key", settings.CORS_ALLOW_HEADERS)
        self.assertIn(self.frontend_origin, settings.CORS_ALLOWED_ORIGINS)

    def test_login_preflight_accepts_idempotency_header_from_frontend(self):
        response = self.client.options(
            "/api/auth/login/",
            HTTP_ORIGIN=self.frontend_origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,idempotency-key",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], self.frontend_origin)
        allowed_headers = {
            header.strip().lower()
            for header in response["Access-Control-Allow-Headers"].split(",")
        }
        self.assertIn("content-type", allowed_headers)
        self.assertIn("idempotency-key", allowed_headers)
