"""Rate limiting (slowapi). Authenticated requests are keyed per user (JWT sub
from the access_token cookie); anonymous requests per client IP. Counters are
in-memory — per-process only (V1). Multi-worker deployments should pass a
Redis storage_uri to Limiter; Redis is already in the stack.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def user_or_ip(request: Request) -> str:
    token = request.cookies.get("access_token")
    if token:
        from backend.services.auth_service import decode_token

        try:
            return f"user:{decode_token(token)}"
        except Exception:
            pass  # bad/expired token → treated as anonymous, keyed by IP
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=user_or_ip,
    default_limits=["100/minute"],
    headers_enabled=True,  # 429s carry Retry-After + X-RateLimit-*
)
