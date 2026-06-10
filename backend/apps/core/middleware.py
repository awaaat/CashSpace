import logging
import time

logger = logging.getLogger("apps.core")


class RequestLoggingMiddleware:
    """Log every request with method, path, status and duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000

        user = getattr(request, "user", None)
        user_str = str(user.id) if user and user.is_authenticated else "anon"

        logger.info(
            "%s %s | %s | user=%s | %.1fms",
            request.method,
            request.path,
            response.status_code,
            user_str,
            duration_ms,
        )
        return response