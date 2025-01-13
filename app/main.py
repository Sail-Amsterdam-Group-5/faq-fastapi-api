from fastapi import FastAPI, HTTPException, Header, status, Request
from pydantic import BaseModel, Field
from azure.data.tables import TableServiceClient, TableEntity, UpdateMode
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from typing import List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
import logging
import uuid
import os
import sys

# Updated requirements.txt 2

# Suppress Azure SDK logs
azure_logger = logging.getLogger("azure")
azure_logger.setLevel(logging.WARNING)  # Log only warnings or above

logging.basicConfig(
    level=logging.INFO,  # Use DEBUG level to ensure all logs are captured
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # Send INFO, DEBUG logs to stdout
        logging.StreamHandler(sys.stderr),  # Send ERROR, CRITICAL logs to stderr
    ],
)

# Initialize FastAPI app
# added a comment to check the workings of workflows v4.0
app = FastAPI()

logger = logging.getLogger(__name__)

internalServerErrorMsg = "Internal server error occurred."
faqNotFoundErrorMsg = "FAQ not found."
failedToFetchFaqErrorMsg = "Failed to fetch FAQ entry"
notFoundExceptionMessage = "No FAQ with the details provided was found."
roleHeaderMissingErrorMsg = "The roles header is missing from the request."
invalidRoleErrorMsg = (
    "You do not have the necessary permissions to perform this action."
)

logger.info("Attempting to retrieve the connection string...")

try:
    # Read connection string from environment variable
    connection_string = os.getenv("FAQ_AZURE_CONN_STRING", "MOCK_CONNECTION_STRING")
    if not connection_string:
        raise ValueError("Environment variable FAQ_AZURE_CONN_STRING is not set.")
except Exception:
    logger.error("Failed to connect to Azure Table Storage")
    raise RuntimeError("Could not connect to Azure Table Storage.")


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if "retrieved_secret.value" in record.getMessage():
            record.msg = record.msg.replace(connection_string, "[REDACTED]")
        return True


logger.addFilter(SensitiveDataFilter())

# Azure Table Storage configuration
TABLE_NAME = "faqs"

logger.info("Initializing Azure Table client for FAQ service...")

try:
    if not connection_string or connection_string == "MOCK_CONNECTION_STRING":
        raise ValueError("Invalid connection string for Azure Table Storage.")
    table_service = TableServiceClient.from_connection_string(connection_string)
    table_client = table_service.create_table_if_not_exists("faqs")
    logger.info("Connected to Azure Table Storage and ensured 'faqs' table exists.")
except ValueError as ve:
    logger.error(f"Connection string error: {ve}")
    table_service = None  # Use None for local/mock environments
    table_client = None
except Exception as e:
    logger.error(f"Failed to initialize Table Storage: {e}")
    raise RuntimeError("Could not initialize Azure Table Storage.") from e

logger.info("Initializing Prometheus metrics for FAQ service...")

# Initialize Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds", "Latency of HTTP requests", ["method", "endpoint"]
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track Prometheus metrics for every request.
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path
        start_time = time.time()

        response = await call_next(request)
        latency = time.time() - start_time
        status_code = response.status_code

        # Update Prometheus metrics
        REQUEST_COUNT.labels(
            method=method, endpoint=endpoint, http_status=status_code
        ).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)

        logger.info(
            f"Request processed in {latency:.3f} seconds with status {status_code}"
        )

        return response


# Add the Prometheus middleware to the FastAPI app
app.add_middleware(MetricsMiddleware)


# Expose the /metrics endpoint for Prometheus to scrape
@app.get("/metrics")
def get_metrics():
    """
    Endpoint to expose Prometheus metrics.
    """
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


# Define Pydantic models for input validation
class FAQEntry(BaseModel):
    question: str = Field(
        ..., min_length=5, max_length=500, description="The FAQ question"
    )
    answer: str = Field(
        ..., min_length=1, max_length=1000, description="The FAQ answer"
    )
    category: str = Field(
        ..., min_length=1, max_length=100, description="Category of the FAQ"
    )
    id: Optional[str] = Field(None, min_length=1, max_length=100)
    clicks: Optional[int] = Field(None)


class FAQUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=5, max_length=500)
    answer: Optional[str] = Field(None, min_length=1, max_length=1000)
    category: Optional[str] = Field(None, min_length=1, max_length=100)


logger.info("FAQ service application initialized and running.")


# FAQ Endpoints:


# POST /faqs: Accepts an FAQEntry and stores it in the database.
# Returns a success message and the inserted data upon success.


@app.post("/faqs", status_code=201)
async def create_faq_entry(faq: FAQEntry, request: Request):
    """
    Endpoint to create a new FAQ entry in Azure Table Storage.
    """
    # Get X-User-Roles from the request headers
    user_roles = request.headers.get("X-User-Roles")
    if not user_roles:
        raise HTTPException(status_code=400, detail=roleHeaderMissingErrorMsg)
    if "admin" not in user_roles:
        raise HTTPException(
            status_code=403,
            detail=invalidRoleErrorMsg,
        )

    # Use category as PartitionKey
    partition_key = faq.category
    row_key = str(uuid.uuid4())  # Unique identifier for the entry

    # Prepare entity for Table Storage
    faq_entity: TableEntity = {
        "PartitionKey": partition_key,
        "RowKey": row_key,
        "Question": faq.question,
        "Answer": faq.answer,
        "Clicks": 0,
    }

    try:
        # Insert the entity into Table Storage
        table_client.create_entity(entity=faq_entity)
        return {
            "message": "FAQ entry created successfully",
            "data": {
                "id": row_key,
                "question": faq.question,
                "answer": faq.answer,
                "category": faq.category,
            },
        }
    except ResourceExistsError:
        raise HTTPException(status_code=409, detail="FAQ entry already exists")
    except Exception:
        logger.error("Failed to create FAQ entry", exc_info=True)
        raise HTTPException(status_code=500, detail=internalServerErrorMsg)


# GET /faqs: Accepts a category to query by and returns all of the results.
# If no category is provided or it is null it returns all FAQs in the db.


@app.get("/faqs", response_model=List[FAQEntry])
async def get_faqs_by_category(
    category: Optional[str] = Header(None, description="Category of the FAQs"),
):
    """
    Get all FAQs filtered by category passed in the header,
    sorted by the 'Clicks' column.
    """
    try:
        if category is not None:
            # Fetch all entries for the specified category
            query_filter = f"PartitionKey eq '{category}'"
        else:
            # If no category is provided, query all entities without filtering
            query_filter = ""

        entities = table_client.query_entities(query_filter)

        # Convert to list and sort by the 'Clicks' column
        faqs = [
            FAQEntry(
                question=entity["Question"],
                answer=entity["Answer"],
                category=entity["PartitionKey"],
                id=entity["RowKey"],
                clicks=entity["Clicks"],
            )
            for entity in entities
        ]

        faqs.sort(key=lambda faq: faq.clicks, reverse=True)

        if not faqs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No FAQs found."
            )

        return faqs

    except HTTPException as http_exception:
        # If it's already an HTTPException (like a 404), raise it as is
        raise http_exception

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# Gets an FAQ based on the PartitionKey (category) and RowKey (faq_id).


@app.get("/faqs/{category}/{faq_id}", response_model=FAQEntry)
async def get_faq_by_id(faq_id: str, category: str):
    """
    Get a FAQ by PartitionKey (category) and RowKey (faq_id).
    """
    try:
        entity = table_client.get_entity(partition_key=category, row_key=faq_id)

        return FAQEntry(
            question=entity["Question"],
            answer=entity["Answer"],
            category=entity["PartitionKey"],
            id=entity["RowKey"],
            clicks=entity["Clicks"],
        )

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=faqNotFoundErrorMsg)

    except Exception:
        logger.error(failedToFetchFaqErrorMsg, exc_info=True)
        raise HTTPException(status_code=500, detail=internalServerErrorMsg)


# PUT: If the FAQUpdate object in the request contains a non-null category
# (i.e. the user wants to update the Partition Key of an existing FAQ)
# copy the entry data, delete the entry and insert a new entry
# with the same data and an altered Partition Key.
# Otherwise, simply update the columns specified by the user.


@app.put("/faqs/{category}/{faq_id}", response_model=FAQEntry)
async def update_faq(faq_id: str, category: str, faq: FAQUpdate, request: Request):
    """
    Update an existing FAQ by PartitionKey (category) and RowKey (faq_id).
    If the category is updated, copy the entity to a new PartitionKey,
    delete the old entry, and insert the new one.
    """

    # Get X-User-Roles from the request headers
    user_roles = request.headers.get("X-User-Roles")
    if not user_roles:
        raise HTTPException(status_code=400, detail=roleHeaderMissingErrorMsg)
    if "admin" not in user_roles:
        raise HTTPException(
            status_code=403,
            detail=invalidRoleErrorMsg,
        )

    try:
        # Fetch the existing FAQ entity
        entity = table_client.get_entity(partition_key=category, row_key=faq_id)

        # Handle category update
        if faq.category and faq.category != category:
            # Copy the existing entity to a new PartitionKey
            new_entity = entity.copy()
            new_entity["PartitionKey"] = faq.category
            new_entity["RowKey"] = faq_id

            # Update fields if specified
            if faq.question:
                new_entity["Question"] = faq.question
            if faq.answer:
                new_entity["Answer"] = faq.answer

            # Insert new entity and delete the old one
            table_client.create_entity(entity=new_entity)
            table_client.delete_entity(partition_key=category, row_key=faq_id)

            # Return the new entity
            return FAQEntry(
                question=new_entity["Question"],
                answer=new_entity["Answer"],
                category=new_entity["PartitionKey"],
                id=new_entity["RowKey"],
                clicks=new_entity.get(
                    "Clicks", 0
                ),  # Include clicks, default to 0 if missing
            )

        else:
            # Only update specified fields for the existing entity
            if faq.question:
                entity["Question"] = faq.question
            if faq.answer:
                entity["Answer"] = faq.answer

            # Update the entity in Table Storage
            table_client.update_entity(entity=entity)

            # Return the updated entity
            return FAQEntry(
                question=entity["Question"],
                answer=entity["Answer"],
                category=entity["PartitionKey"],
                id=entity["RowKey"],
                clicks=entity.get(
                    "Clicks", 0
                ),  # Include clicks, default to 0 if missing
            )

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=faqNotFoundErrorMsg)

    except Exception:
        logger.error(failedToFetchFaqErrorMsg, exc_info=True)
        raise HTTPException(status_code=500, detail=internalServerErrorMsg)


# DELETE: Deletes an entry in the database with the faq_id specified


@app.delete("/faqs/{category}/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(faq_id: str, category: str, request: Request):
    """
    Delete an FAQ by PartitionKey (category) and RowKey (faq_id).
    """

    # Get X-User-Roles from the request headers
    user_roles = request.headers.get("X-User-Roles")
    if not user_roles:
        raise HTTPException(status_code=400, detail=roleHeaderMissingErrorMsg)
    if "admin" not in user_roles:
        raise HTTPException(
            status_code=403,
            detail=invalidRoleErrorMsg,
        )

    try:
        # Delete the FAQ entity
        table_client.delete_entity(partition_key=category, row_key=faq_id)
        return {"message": "FAQ deleted successfully."}

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=faqNotFoundErrorMsg)

    except Exception:
        logger.error(failedToFetchFaqErrorMsg, exc_info=True)
        raise HTTPException(status_code=500, detail=internalServerErrorMsg)


# POST: Increments the Clicks column of the row with the specified Partition
# and RowKey (category and faq_id respectively) by 1 when called.


@app.post("/faqs/{category}/{faq_id}/click")
async def increment_clicks(category: str, faq_id: str):
    """
    Increment the Clicks column for an FAQ
    by PartitionKey (category) and RowKey (faq_id).
    """
    try:
        # Fetch the entity to get the current Clicks value
        entity = table_client.get_entity(partition_key=category, row_key=faq_id)

        # Increment the Clicks value
        current_clicks = entity["Clicks"]  # Default to 0 if Clicks is not set
        entity["Clicks"] = current_clicks + 1

        # Update the entity back into the table
        table_client.update_entity(entity, mode=UpdateMode.REPLACE)

        # Log or return data properly, ensuring integers are converted to str
        return {
            "detail": "Clicks incremented successfully.",
            "new_clicks": entity["Clicks"],  # No concatenation here
        }

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail=faqNotFoundErrorMsg)

    except Exception:
        logger.error(failedToFetchFaqErrorMsg, exc_info=True)
        raise HTTPException(status_code=500, detail=internalServerErrorMsg)
