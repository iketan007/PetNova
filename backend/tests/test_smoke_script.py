"""Offline regression tests for the non-destructive deployment smoke checker."""
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_test_deployment.py"
spec = importlib.util.spec_from_file_location("petnova_smoke_test_deployment", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)


class FakeResponse:
    def __init__(self, status=200, body=b"ok", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


class SmokeScriptHttpTests(unittest.TestCase):
    def test_request_returns_status_headers_and_body(self):
        with patch.object(smoke.urllib.request, "urlopen", return_value=FakeResponse()):
            status, headers, body = smoke.request("https://example.invalid/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(body, b"ok")

    def test_http_error_is_reported_as_status_for_assertion(self):
        error = HTTPError("https://example.invalid/health", 503, "unavailable", {}, io.BytesIO(b"down"))
        with patch.object(smoke.urllib.request, "urlopen", side_effect=error):
            status, _headers, body = smoke.request("https://example.invalid/health")
        self.assertEqual(status, 503)
        self.assertEqual(body, b"down")

    def test_network_error_is_wrapped_without_credentials(self):
        with patch.object(smoke.urllib.request, "urlopen", side_effect=URLError("offline")):
            with self.assertRaises(smoke.SmokeFailure) as caught:
                smoke.request("https://example.invalid/health")
        self.assertIn("request failed", str(caught.exception))
        self.assertNotIn("token", str(caught.exception).lower())

    def test_expect_status_rejects_unexpected_status(self):
        with patch.object(smoke, "request", return_value=(503, {}, b"maintenance")):
            with self.assertRaisesRegex(smoke.SmokeFailure, "got 503"):
                smoke.expect_status("https://example.invalid/health")


if __name__ == "__main__":
    unittest.main()
