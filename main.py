from fastapi import FastAPI, HTTPException, Header, status
from pydantic import BaseModel, Field
from azure.data.tables import TableServiceClient, TableEntity
from typing import List, Optional
import uuid

# Initialize FastAPI app
app = FastAPI()

# Azure Table Storage configuration
AZURE_CONNECTION_STRING = "UseDevelopmentStorage=true"  # Azurite default connection string
TABLE_NAME = "FAQs"

# Initialize TableServiceClient
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

class FAQUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=5, max_length=500)
    answer: Optional[str] = Field(None, min_length=1, max_length=1000)
    category: Optional[str] = Field(None, min_length=1, max_length=100)

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create FAQ entry: {str(e)}")

@app.get("/faqs", response_model=List[FAQEntry])
async def get_faqs_by_category(category: Optional[str] = Header(None, description="Category of the FAQs")):
    """
    Get all FAQs filtered by category passed in the header.
    """
    try:
        if category is not None:
            # Fetch all entries for the specified category
            query_filter = f"PartitionKey eq '{category}'"
        else:
            # If no category is provided, query all entities without filtering by category
            query_filter = ""
        
        entities = table_client.query_entities(query_filter)
        
        faqs = [
            FAQEntry(
                question=entity["Question"],
                answer=entity["Answer"],
                category=entity["PartitionKey"]
            )
            for entity in entities
        ]
        
        if not faqs:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No FAQs found.")
        
        return faqs
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.get("/faqs/{faq_id}", response_model=FAQEntry)
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
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found.")


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
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found.")


@app.delete("/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(faq_id: str, category: str):
    """
    Delete an FAQ by PartitionKey (category) and RowKey (faq_id).
    """
    try:
        # Delete the FAQ entity
        table_client.delete_entity(partition_key=category, row_key=faq_id)
        return {"message": "FAQ deleted successfully."}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found." + e)