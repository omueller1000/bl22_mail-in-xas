"""Request size limit.

The largest legitimate request is a raw sweep upload (typically ~1 MB, up to ~5 MB as JSON);
anything far beyond that is refused before it is read. nginx enforces the same limit in front.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

MAX_REQUEST_BYTES = 12 * 1024 * 1024


async def limit_body_size(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        return JSONResponse(
            {"detail": f"Request larger than {MAX_REQUEST_BYTES // (1024 * 1024)} MB"},
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
    return await call_next(request)
