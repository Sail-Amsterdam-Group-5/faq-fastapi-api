from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import time

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds", "Latency of HTTP requests", ["method", "endpoint"]
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path
        start_time = time.time()

        response = await call_next(request)
        latency = time.time() - start_time
        status_code = response.status_code

        REQUEST_COUNT.labels(
            method=method, endpoint=endpoint, http_status=status_code
        ).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)

        return response
