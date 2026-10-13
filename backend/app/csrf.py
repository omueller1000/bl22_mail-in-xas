"""Protection against cross-site request forgery for cookie-authenticated requests.

SameSite cookies alone are not enough here: every *.stanford.edu site counts as the "same
site". So every state-changing request must carry a custom header. A browser only sends custom
headers cross-origin after a CORS preflight, which this API never approves; other sites
therefore cannot forge such requests with the user's session cookie.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "ht-xas"

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_middleware(
    api_prefix: str,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    # Instrument endpoints authenticate with an API key, not a cookie, so CSRF does not apply.
    exempt_prefix = f"{api_prefix}/instrument/"

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            request.method not in _SAFE_METHODS
            and not request.url.path.startswith(exempt_prefix)
            and request.headers.get(CSRF_HEADER) != CSRF_VALUE
        ):
            return JSONResponse(
                {"detail": f"Missing {CSRF_HEADER} header"}, status.HTTP_403_FORBIDDEN
            )
        return await call_next(request)

    return middleware
