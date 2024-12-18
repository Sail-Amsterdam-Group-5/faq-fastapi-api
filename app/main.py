from fastapi import FastAPI, HTTPException, Header, status
from pydantic import BaseModel, Field
from azure.data.tables import TableServiceClient, TableEntity, UpdateMode
from typing import List, Optional, Dict  # For testing with mock storage
from unittest.mock import MagicMock  # For testing with mock storage
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
import logging
import uuid

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

logging.basicConfig(level=logging.ERROR)

KEY_VAULT_URL = "https://sailfaqdatabasedevcred.vault.azure.net/"

credential = DefaultAzureCredential()

# Get secret from Azure Key Vault
secret_name = "sail-faq-dev-database-conn"
secret_client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
retrieved_secret = secret_client.get_secret(secret_name)

# Initialize FastAPI app
# added a comment to check the workings of workflows v4.0
app = FastAPI()

logger = logging.getLogger(__name__)

class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if "retrieved_secret.value" in record.getMessage():
            record.msg = record.msg.replace(retrieved_secret.value, "[REDACTED]")
        return True

logger.addFilter(SensitiveDataFilter())

# Azure Table Storage configuration
AZURE_CONNECTION_STRING = f"{retrieved_secret.value}"  # Azure conn string
TABLE_NAME = "faqs"

notFoundExceptionMessage = "No FAQ with the details provided was found."

# Initialize TableServiceClient
table_service = TableServiceClient.from_connection_string(AZURE_CONNECTION_STRING)

# Ensure the table exists
try:
    table_client = table_service.create_table_if_not_exists(TABLE_NAME)
except Exception as e:
    logger.error("Failed to initialize Table Storage: %s", str(e))
    raise RuntimeError(
        "Failed to initialize Table Storage. Please check the logs for details."
    )


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


# FAQ Endpoints:


# POST /faqs: Accepts an FAQEntry and stores it in the database. Returns a success message and the inserted data upon success.


@app.post("/faqs", status_code=201)
async def create_faq_entry(faq: FAQEntry):
    """
    Endpoint to create a new FAQ entry in Azure Table Storage.
    """
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
        raise HTTPException(status_code=409, detail="FAQ entry already exists.")
    except Exception as e:
        logger.error("Failed to create FAQ entry", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error occurred.")


# GET /faqs: Accepts a category to query by and returns all of the results. If no category is provided or it is null it returns all FAQs stored in the database.


@app.get("/faqs", response_model=List[FAQEntry])
async def get_faqs_by_category(
    category: Optional[str] = Header(None, description="Category of the FAQs"),
):
    """
    Get all FAQs filtered by category passed in the header, sorted by the 'Clicks' column.
    """
    try:
        if category is not None:
            # Fetch all entries for the specified category
            query_filter = f"PartitionKey eq '{category}'"
        else:
            # If no category is provided, query all entities without filtering by category
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


# GET /faqs/{faq_id}: Gets an FAQ based on the partition key (category) and row key (faq_id).


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
        )

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    
    except Exception:
        logger.error("Failed to fetch FAQ entry", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error occurred.")


# PUT /faqs/{category}/{faq_id}: If the FAQUpdate object in the request contains a non-null category (i.e. the user wants to update the Partition Key of an existing FAQ) copy the entry data, delete the entry and insert a new entry with the same data and an altered Partition Key. Otherwise, simply update the columns specified by the user.


@app.put("/faqs/{category}/{faq_id}", response_model=FAQEntry)
async def update_faq(faq_id: str, category: str, faq: FAQUpdate):
    """
    Update an existing FAQ by PartitionKey (category) and RowKey (faq_id).
    If the category is updated, copy the entity to a new PartitionKey, delete the old entry, and insert the new one.
    """
    try:
        # Fetch the existing FAQ entity
        entity = table_client.get_entity(partition_key=category, row_key=faq_id)

        # Handle category update
        if faq.category and faq.category != category:
            # Copy the existing entity to a new PartitionKey
            new_entity = entity.copy()
            new_entity["PartitionKey"] = faq.category  # Update category (PartitionKey)
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
        raise HTTPException(status_code=404, detail="FAQ not found.")
    
    except Exception:
        logger.error("Failed to fetch FAQ entry", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error occurred.")


# DELETE /faqs/{faq_id}: Deletes an entry in the database with the faq_id specified


@app.delete("/faqs/{category}/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(faq_id: str, category: str):
    """
    Delete an FAQ by PartitionKey (category) and RowKey (faq_id).
    """
    try:
        # Delete the FAQ entity
        table_client.delete_entity(partition_key=category, row_key=faq_id)
        return {"message": "FAQ deleted successfully."}

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    
    except Exception:
        logger.error("Failed to fetch FAQ entry", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error occurred.")


# POST /faqs/{category}/{faq_id}: Increments the Clicks column of the row with the specified Partition and RowKey (category and faq_id respectively) by 1 when called.


@app.post("/faqs/{category}/{faq_id}/click")
async def increment_clicks(category: str, faq_id: str):
    """
    Increment the Clicks column for a FAQ by PartitionKey (category) and RowKey (faq_id).
    """
    try:
        # Fetch the entity to get the current Clicks value
        entity = table_client.get_entity(partition_key=category, row_key=faq_id)

        # Increment the Clicks value
        current_clicks = entity["Clicks"]  # Default to 0 if Clicks is not set
        entity["Clicks"] = current_clicks + 1

        # Update the entity back into the table
        table_client.update_entity(entity, mode=UpdateMode.REPLACE)

        # Log or return data properly, ensuring integers are converted to strings
        return {
            "detail": "Clicks incremented successfully.",
            "new_clicks": entity["Clicks"],  # No concatenation here
        }

    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    
    except Exception:
        logger.error("Failed to fetch FAQ entry", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error occurred.")
