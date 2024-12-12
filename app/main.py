from fastapi import FastAPI, HTTPException, Header, status
from pydantic import BaseModel, Field
from azure.data.tables import TableServiceClient, TableEntity
from typing import List, Optional, Dict # For testing with mock storage
from unittest.mock import MagicMock # For testing with mock storage
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
import logging
import uuid

# Initialize FastAPI app
app = FastAPI()

logger = logging.getLogger(__name__)

# Azure Table Storage configuration
AZURE_CONNECTION_STRING = "UseDevelopmentStorage=true"  # Azurite default connection string
TABLE_NAME = "FAQs"

notFoundExceptionMessage = "No FAQ with the details provided was found."

#Initialize TableServiceClient
table_service = TableServiceClient.from_connection_string(AZURE_CONNECTION_STRING)

# Ensure the table exists
try:
    table_client = table_service.create_table_if_not_exists(TABLE_NAME)
except Exception as e:
    raise RuntimeError(f"Failed to initialize Table Storage: {e}")

# Define Pydantic models for input validation
class FAQEntry(BaseModel):
    question: str = Field(..., min_length=5, max_length=500, description="The FAQ question")
    answer: str = Field(..., min_length=1, max_length=1000, description="The FAQ answer")
    category: str = Field(..., min_length=1, max_length=100, description="Category of the FAQ")
    id: Optional[str] = Field(None, min_length=1, max_length=100)
    clicks: Optional[int] = Field(...)

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
        "Clicks": 0
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
        logger.error(f"Error creating FAQ: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred.")

# GET /faqs: Accepts a category to query by and returns all of the results. If no category is provided or it is null it returns all FAQs stored in the database.

@app.get("/faqs", response_model=List[FAQEntry])
async def get_faqs_by_category(category: Optional[str] = Header(None, description="Category of the FAQs")):
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
                clicks=entity["Clicks"]
            )
            for entity in entities
        ]

        faqs.sort(key=lambda faq: faq.clicks, reverse=True)

        if not faqs:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No FAQs found.")

        return faqs

    except HTTPException as http_exception:
        # If it's already an HTTPException (like a 404), raise it as is
        raise http_exception

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
            category=entity["PartitionKey"]
        )
    
    except HTTPException as http_exception:
        # If it's already an HTTPException (like a 404), raise it as is
        raise http_exception
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    

@app.put("/faqs/{faq_id}", response_model=FAQEntry)
async def update_faq(faq_id: str, category: str, faq: FAQUpdate):
    """
    Update an existing FAQ by PartitionKey (category) and RowKey (faq_id).
    """
    try:
        # Fetch the existing FAQ entity
        entity = table_client.get_entity(partition_key=category, row_key=faq_id)
        
        # Only update non-None fields
        if faq.question:
            entity["Question"] = faq.question
        if faq.answer:
            entity["Answer"] = faq.answer
        if faq.category:
            entity["Category"] = faq.category  # You can also choose to not change category
        
        # Update the entity in Table Storage
        table_client.update_entity(entity=entity)
        
        return FAQEntry(
            question=entity["Question"],
            answer=entity["Answer"],
            category=entity["Category"]
        )
    
    except HTTPException as http_exception:
        # If it's already an HTTPException (like a 404), raise it as is
        raise http_exception
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# DELETE /faqs/{faq_id}: Deletes an entry in the database with the faq_id specified

@app.delete("/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(faq_id: str, category: str):
    """
    Delete an FAQ by PartitionKey (category) and RowKey (faq_id).
    """
    try:
        # Delete the FAQ entity
        table_client.delete_entity(partition_key=category, row_key=faq_id)
        return {"message": "FAQ deleted successfully."}
    
    except HTTPException as http_exception:
        # If it's already an HTTPException (like a 404), raise it as is
        raise http_exception
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))