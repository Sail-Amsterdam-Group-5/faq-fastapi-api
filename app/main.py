from fastapi import FastAPI, HTTPException, Header, status
from pydantic import BaseModel, Field
from azure.data.tables import TableEntity
from typing import List, Optional, Dict  # For testing with mock storage
from azure.core.exceptions import ResourceExistsError
import logging
import uuid

# Initialize FastAPI app
# added a comment to check the workings of workflows v4.0
app = FastAPI()

# Test

logger = logging.getLogger(__name__)

# Azure Table Storage configuration
AZURE_CONNECTION_STRING = (
    "UseDevelopmentStorage=true"  # Azurite default connection string
)
TABLE_NAME = "FAQs"

notFoundExceptionMessage = "No FAQ with the details provided was found."

# Initialize TableServiceClient
# table_service = TableServiceClient.
# from_connection_string(AZURE_CONNECTION_STRING)

# # Ensure the table exists
# try:
#     table_client = table_service.create_table_if_not_exists(TABLE_NAME)
# except Exception as e:
#     raise RuntimeError(f"Failed to initialize Table Storage: {e}")


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


class FAQUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=5, max_length=500)
    answer: Optional[str] = Field(None, min_length=1, max_length=1000)
    category: Optional[str] = Field(None, min_length=1, max_length=100)


# Fake table client for openshift testing purposes


# Mock Table Storage
class MockTableClient:
    def __init__(self):
        self.data = []  # Fake in-memory table storage

    def create_table_if_not_exists(self, table_name: str):
        """Mock table creation."""
        if table_name != TABLE_NAME:
            raise ValueError(f"Unknown table: {table_name}")
        return self  # Return the mock itself to mimic a real client

    def create_entity(self, entity: Dict):
        """Mock entity insertion/upsertion."""
        self.data.append(entity)

    def list_entities(self) -> List[Dict]:
        """Mock retrieval of all entities."""
        return self.data

    def query_entities(self) -> List[Dict]:
        """Mock querying entities."""
        # For simplicity, just return all FAQs for now
        return self.data

    def update_entity(self, entity: Dict):
        """Mock entity insertion/upsertion."""
        # Update if RowKey exists
        for i, existing_entity in enumerate(self.data):
            if (
                existing_entity["PartitionKey"] == entity["PartitionKey"]
                and existing_entity["RowKey"] == entity["RowKey"]
            ):
                self.data[i] = entity  # Update existing entity
                return


# Inject mock TableClient
table_service = MockTableClient()
table_client = table_service.create_table_if_not_exists(TABLE_NAME)

# FAQ Endpoints:

# POST /faqs: Accepts an FAQEntry and stores it in the database.
# Returns a success message and the inserted data upon success.


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
    except ResourceExistsError:
        raise HTTPException(status_code=409, detail="FAQ entry already exists.")
    except Exception as e:
        logger.error(f"Error creating FAQ: {e}")
        raise HTTPException(status_code=500, detail="Internal server error occurred.")


# GET /faqs: Accepts a category to query by and returns all of the results.
# If no category is provided or it is null it returns all FAQs stored in the database.


@app.get("/faqs", response_model=List[FAQEntry])
async def get_faqs_by_category(
    category: Optional[str] = Header(None, description="Category of the FAQs")
):
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
                category=entity["PartitionKey"],
                id=entity["RowKey"],
            )
            for entity in entities
        ]

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

    except HTTPException as http_exception:
        # If it's already an HTTPException (like a 404), raise it as is
        raise http_exception

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


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
            entity["Category"] = (
                faq.category
            )  # You can also choose to not change category

        # Update the entity in Table Storage
        table_client.update_entity(entity=entity)

        return FAQEntry(
            question=entity["Question"],
            answer=entity["Answer"],
            category=entity["Category"],
        )

    except HTTPException as http_exception:
        # If it's already an HTTPException (like a 404), raise it as is
        raise http_exception

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# Testing Endpoint


@app.get("/mock/data")
async def mock_data():
    """Populate mock data for testing."""
    mock_faqs = [
        {
            "PartitionKey": "FAQ",
            "RowKey": str(index + 1),
            "Question": faq.question,
            "Answer": faq.answer,
            "Category": faq.category,
        }
        for index, faq in enumerate(
            [
                FAQEntry(
                    question="Where do I pick up my volunteer badge?",
                    answer="You can pick up your volunteer badge at the Volunteer Check-in Desk, located at the main event entrance. Please bring a valid ID for verification.",
                    category="General",
                ),
                FAQEntry(
                    question="What time should I arrive for my volunteer shift?",
                    answer="Please arrive at least 30 minutes before your scheduled shift time to check in, receive your materials, and attend any necessary briefing sessions.",
                    category="Schedule",
                ),
                FAQEntry(
                    question="Who do I contact if I have a problem during my shift?",
                    answer="If you encounter any issues during your shift, contact your Volunteer Coordinator or head to the Volunteer Support Desk, where staff will be available to assist you.",
                    category="Support",
                ),
                FAQEntry(
                    question="What should I wear as a volunteer?",
                    answer="As a volunteer, you will be provided with an official SAIL Amsterdam t-shirt, hat, and safety vest. Please wear comfortable clothing and closed-toe shoes, and ensure you're prepared for the weather.",
                    category="Guidelines",
                ),
                FAQEntry(
                    question="What are my responsibilities as a volunteer?",
                    answer="""Your responsibilities may include guiding visitors, assisting with event logistics, helping at information points, and ensuring safety protocols are followed during activities.
                    Each role may vary, and you’ll receive detailed instructions beforehand.""",
                    category="Responsibilities",
                ),
                FAQEntry(
                    question="Is there a place for volunteers to take breaks?",
                    answer="Yes, there will be a designated Volunteer Rest Area where you can take breaks during your shift. You’ll be given more details about its location during your orientation.",
                    category="Facilities",
                ),
                FAQEntry(
                    question="How do I get access to restricted areas?",
                    answer="Access to restricted areas will be granted based on your volunteer role. Your badge will indicate the areas you're authorized to enter. If you're unsure, please check with a Volunteer Coordinator.",
                    category="Access",
                ),
                FAQEntry(
                    question="What do I do if I need to change or cancel my shift?",
                    answer="If you need to change or cancel your shift, please contact the Volunteer Coordinator as soon as possible. They will help you reschedule or find someone to cover your shift.",
                    category="Schedule",
                ),
                FAQEntry(
                    question="Will food and drinks be provided for volunteers?",
                    answer="Yes, volunteers will be provided with complimentary meals and drinks during their shifts. Specific meal times and locations will be communicated in advance.",
                    category="Facilities",
                ),
                FAQEntry(
                    question="Who is responsible for my safety during the event?",
                    answer="Your safety is our priority. Volunteer Coordinators and safety officers will be available throughout the event to ensure that all safety guidelines are followed. Please report any safety concerns immediately.",
                    category="Safety",
                ),
                FAQEntry(
                    question="What happens if I am running late for my shift?",
                    answer="If you're running late, please inform your Volunteer Coordinator as soon as possible. If you can't reach them directly, contact the Volunteer Support Desk for assistance.",
                    category="Schedule",
                ),
                FAQEntry(
                    question="Can I switch shifts with another volunteer?",
                    answer="Yes, you can switch shifts with another volunteer as long as both of you inform the Volunteer Coordinator beforehand to ensure there is no overlap or staffing issues.",
                    category="Schedule",
                ),
                FAQEntry(
                    question="Will there be any training for my role?",
                    answer="Yes, all volunteers will attend an orientation and training session before the festival begins. The training will cover your responsibilities, safety protocols, and other important event details.",
                    category="Training",
                ),
                FAQEntry(
                    question="Can I volunteer with a friend or family member?",
                    answer="You can request to be scheduled for shifts with a friend or family member, but it depends on availability and the roles required. Please mention this during the sign-up process.",
                    category="General",
                ),
                FAQEntry(
                    question="What should I do if I lose my volunteer badge?",
                    answer="If you lose your volunteer badge, immediately report it to the Volunteer Support Desk. A replacement badge will be issued after verification.",
                    category="Access",
                ),
                FAQEntry(
                    question="Can I leave the event early if I finish my shift early?",
                    answer="If you finish your shift early, please check in with your Volunteer Coordinator. Depending on the event's needs, you may be asked to stay longer or assist in other areas.",
                    category="Schedule",
                ),
                FAQEntry(
                    question="What should I do if I witness an emergency or accident?",
                    answer="If you witness an emergency or accident, immediately report it to the nearest staff member or Volunteer Coordinator. Follow the emergency protocols provided during your training to ensure proper action is taken.",
                    category="Safety",
                ),
                FAQEntry(
                    question="Are there any specific COVID-19 precautions for volunteers?",
                    answer="Yes, specific COVID-19 protocols will be in place to ensure everyone's safety. These may include mask-wearing, social distancing, and hand sanitizing. Detailed guidelines will be shared before the event.",
                    category="Safety",
                ),
                FAQEntry(
                    question="How do I receive my volunteer certificate after the event?",
                    answer="After the event, volunteers will receive a certificate of participation via email. This will be sent within a few weeks following the conclusion of the festival.",
                    category="General",
                ),
                FAQEntry(
                    question="What is the dress code for volunteers?",
                    answer="Volunteers are expected to wear the provided event t-shirt, hat, and safety vest. Please also wear comfortable, weather-appropriate clothing and closed-toe shoes for safety.",
                    category="Guidelines",
                ),
            ]
        )
    ]

    table_client.data.extend(mock_faqs)
    return {"message": "Mock data added successfully!", "data": mock_faqs}
