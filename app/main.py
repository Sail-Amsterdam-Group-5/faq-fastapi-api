from fastapi import FastAPI
from controllers.faq_controller import router as faq_router
from utils.logging_config import setup_logger
from utils.metrics_middleware import MetricsMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

# Test
# Test 2.0
# Test 3.0

# Initialize logger
logger = setup_logger()

# Create FastAPI app
app = FastAPI()

# Add middleware
app.add_middleware(MetricsMiddleware)

# Include routes
app.include_router(faq_router)


# Prometheus metrics endpoint
@app.get("/metrics")
def get_metrics():
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


logger.info("Application has started.")
