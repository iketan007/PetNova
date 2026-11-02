#!/usr/bin/env python3
"""Non-destructive PetNova deployment smoke checks.

Examples:
  PETNOVA_BACKEND_URL=https://vetgpt-backend.onrender.com \
  PETNOVA_FRONTEND_URL=https://vetgpt-ai-hxcr.vercel.app \
  python scripts/smoke_test_deployment.py

Optional authenticated read-only checks:
  PETNOVA_SMOKE_EMAIL=... PETNOVA_SMOKE_PASSWORD=... python scripts/smoke_test_deployment.py

AI chat is opt-in because it calls the configured LLM:
  python scripts/smoke_test_deployment.py --check-chat
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BACKEND = os.getenv("PETNOVA_BACKEND_URL", "https://vetgpt-backend.onrender.com").rstrip("/")
FRONTEND = os.getenv("PETNOVA_FRONTEND_URL", "https://vetgpt-ai-hxcr.vercel.app").rstrip("/")
TIMEOUT = float(os.getenv("PETNOVA_SMOKE_TIMEOUT", "20"))


class SmokeFailure(Exception):
    pass


def request(url, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json"}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            body = response.read()
            return response.status, response.headers, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()
    except Exception as exc:
        raise SmokeFailure(f"request failed for {url}: {type(exc).__name__}: {exc}") from exc


def check(name, fn, results):
    try:
        detail = fn()
        results.append((name, True, detail or "OK"))
    except Exception as exc:
        results.append((name, False, str(exc)))


def expect_status(url, expected=(200,), **kwargs):
    status, _headers, body = request(url, **kwargs)
    if status not in expected:
        snippet = body[:180].decode("utf-8", errors="replace").replace("\n", " ")
        raise SmokeFailure(f"expected HTTP {expected}, got {status}; response={snippet!r}")
    return f"HTTP {status}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-chat", action="store_true", help="Send one small AI chat request (may use provider quota).")
    args = parser.parse_args()
    results = []

    check("Backend health", lambda: expect_status(BACKEND + "/health"), results)
    check("Backend API docs", lambda: expect_status(BACKEND + "/docs"), results)

    def frontend_check():
        status, headers, body = request(FRONTEND)
        if status != 200:
            raise SmokeFailure(f"expected HTTP 200, got {status}")
        content_type = headers.get("Content-Type", "")
        if "text/html" not in content_type.lower() and b"<html" not in body[:1000].lower():
            raise SmokeFailure(f"response does not look like HTML (Content-Type={content_type!r})")
        return f"HTTP {status}; {content_type}"

    check("Frontend page", frontend_check, results)

    email = os.getenv("PETNOVA_SMOKE_EMAIL", "").strip()
    password = os.getenv("PETNOVA_SMOKE_PASSWORD", "")
    token = None
    if email and password:
        def login_check():
            nonlocal token
            status, _headers, body = request(
                BACKEND + "/auth/login", method="POST",
                payload={"email": email, "password": password},
            )
            if status != 200:
                raise SmokeFailure(f"login returned HTTP {status}; verify the dedicated smoke-test account")
            try:
                response = json.loads(body)
                token = response["token"]
            except Exception as exc:
                raise SmokeFailure("login response did not contain a token") from exc
            return "login succeeded (token not displayed)"

        check("Authentication login", login_check, results)
        if token:
            auth = {"Authorization": "Bearer " + token}
            for label, path, key in [
                ("Authenticated profile", "/auth/me", "user"),
                ("Pet records read", "/pets", "pets"),
                ("Health records read", "/health-records", "records"),
                ("Reminders read", "/reminders", "reminders"),
            ]:
                def endpoint_check(path=path, key=key):
                    status, _headers, body = request(BACKEND + path, headers=auth)
                    if status != 200:
                        raise SmokeFailure(f"expected HTTP 200, got {status}")
                    try:
                        payload = json.loads(body)
                    except Exception as exc:
                        raise SmokeFailure("response was not valid JSON") from exc
                    if key not in payload:
                        raise SmokeFailure(f"response missing expected field {key!r}")
                    value = payload[key]
                    count = len(value) if isinstance(value, list) else 1
                    return f"HTTP 200; response field {key!r} present; item count={count}"
                check(label, endpoint_check, results)
    else:
        results.append(("Authenticated workspace checks", None,
                        "SKIPPED; set PETNOVA_SMOKE_EMAIL and PETNOVA_SMOKE_PASSWORD for a dedicated test account"))

    if args.check_chat:
        def chat_check():
            status, _headers, body = request(
                BACKEND + "/chat", method="POST",
                payload={"message": "Reply with a short greeting."},
            )
            if status != 200:
                snippet = body[:180].decode("utf-8", errors="replace").replace("\n", " ")
                raise SmokeFailure(f"expected HTTP 200, got {status}; response={snippet!r}")
            payload = json.loads(body)
            if not isinstance(payload.get("answer"), str) or not payload["answer"].strip():
                raise SmokeFailure("chat response has no answer text")
            return "HTTP 200; non-empty answer returned"
        check("AI chat (provider quota may be used)", chat_check, results)
    else:
        results.append(("AI chat", None, "SKIPPED; pass --check-chat to send one LLM request"))

    print("PetNova deployment smoke-check results")
    failures = 0
    for name, passed, detail in results:
        label = "PASS" if passed is True else "FAIL" if passed is False else "SKIP"
        print(f"[{label}] {name}: {detail}")
        failures += passed is False
    print(f"\nSummary: {sum(p is True for _, p, _ in results)} passed, {failures} failed, {sum(p is None for _, p, _ in results)} skipped.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
