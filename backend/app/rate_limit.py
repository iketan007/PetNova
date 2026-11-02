"""Small per-process fixed-window rate limiting for sensitive public endpoints.

This is a safety net for a single API process, not a substitute for an edge/WAF
rate limiter. Counters reset when the process restarts and are not shared across
multiple workers or instances.
"""
from collections import defaultdict
from threading import Lock
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# method/path -> (maximum requests, window seconds)
LIMITS = {
    ("POST", "/auth/register"): (5, 60),
    ("POST", "/auth/login"): (10, 60),
    ("POST", "/chat"): (20, 60),
    ("POST", "/reindex"): (3, 60),
}

_BUCKETS = defaultdict(list)
_LOCK = Lock()


def reset_rate_limit_state():
    """Clear counters; exposed for deterministic tests."""
    with _LOCK:
        _BUCKETS.clear()


class SensitiveEndpointRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rule = LIMITS.get((request.method.upper(), request.url.path))
        if rule is None:
            return await call_next(request)

        limit, window = rule
        # Use ASGI's resolved client address. In production, ensure the host
        # config only trusts forwarding headers from its own reverse proxy.
        client_ip = request.client.host if request.client else "unknown"
        key = (client_ip, request.method.upper(), request.url.path)
        now = monotonic()
        with _LOCK:
            timestamps = [stamp for stamp in _BUCKETS[key] if now - stamp < window]
            if len(timestamps) >= limit:
                retry_after = max(1, int(window - (now - timestamps[0])))
                _BUCKETS[key] = timestamps
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please wait before trying again."},
                    headers={"Retry-After": str(retry_after)},
                )
            timestamps.append(now)
            _BUCKETS[key] = timestamps

        return await call_next(request)
