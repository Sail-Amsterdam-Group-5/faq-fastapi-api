import logging.config
from fastapi import FastAPI
from controllers.faq_controller import router as faq_router
from utils.metrics_middleware import MetricsMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import logging


# Create FastAPI app
app = FastAPI()

# Suppress Azure SDK logs
azure_logger = logging.getLogger("azure")
azure_logger.setLevel(logging.WARNING)  # Log only warnings or above

# Creates logger
logging.config.fileConfig("app/logging_config.conf", disable_existing_loggers=False)
logger = logging.getLogger(__name__)

logger.info("Attaching middleware...")

# Add middleware
app.add_middleware(MetricsMiddleware)

logger.info("Middleware attached.")

logger.info("Attaching routes...")

# Include routes
app.include_router(faq_router)

logger.info("Routes attached.")

logger.info("Initializing prometheus metrics...")


# Prometheus metrics endpoint
@app.get("/metrics")
def get_metrics():
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


logger.info("Application has started.")
