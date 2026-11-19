from fastapi import Request
from starlette.responses import JSONResponse
import os
import secrets

ALLOWED_ROUTES = [
    "/",
    "/docs"
]

async def api_authenticate_key(request: Request, call_next):
    if request.url.path in ALLOWED_ROUTES:
        return await call_next(request)
    if not request.url.path.startswith("/ai/"):
        return await call_next(request)
    
    api_key = request.headers.get("X-API-KEY")
    expected_key = os.getenv("AUTHENTICATED_KEY") or os.getenv("SECRET_KEY")

    # Keep local development and health checks usable when authentication is
    # not configured; when configured, require a supplied matching key.
    if expected_key and (not api_key or not secrets.compare_digest(api_key, expected_key)):
        return JSONResponse(
            status_code=403,
            content={"detail": "Backend API key is missing or invalid."},
        )
    return await call_next(request)
    # if "X-API_KEY" in request.headers and request.headers["X-API-KEY"] == os.getenv("AUTHENTICATED_KEY"):
    #     call_next(request)
    # return {
    #     "message": "Unauthorized Request"
    # }
