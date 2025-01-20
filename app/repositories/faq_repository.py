from azure.data.tables import TableServiceClient, TableEntity, UpdateMode
from azure.core.exceptions import ResourceNotFoundError
from models.faq_models import FAQEntry, FAQUpdate
from fastapi import HTTPException
import uuid
import os
import logging
from typing import Optional

connection_string = os.getenv("FAQ_AZURE_CONN_STRING", "UseDevelopmentStorage=true")
TABLE_NAME = "faqs"


class FAQRepository:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.table_service = TableServiceClient.from_connection_string(
            connection_string
        )
        self.table_client = self.table_service.create_table_if_not_exists(TABLE_NAME)

    def create_faq_entry(self, faq: FAQEntry):
        partition_key = faq.category
        row_key = str(uuid.uuid4())
        faq_entity: TableEntity = {
            "PartitionKey": partition_key,
            "RowKey": row_key,
            "Question": faq.question,
            "Answer": faq.answer,
            "Clicks": 0,
        }
        self.table_client.create_entity(entity=faq_entity)
        return {
            "message": "FAQ entry created successfully",
            "data": {**faq.dict(), "id": row_key},
        }

    def get_faqs_by_category(self, category: Optional[str] = None):
        query_filter = f"PartitionKey eq '{category}'" if category else ""
        entities = self.table_client.query_entities(query_filter)
        return [
            FAQEntry(
                question=entity["Question"],
                answer=entity["Answer"],
                category=entity["PartitionKey"],
                id=entity["RowKey"],
                clicks=entity["Clicks"],
            )
            for entity in entities
        ]

    def get_faq_by_id(self, category: str, faq_id: str):
        try:
            entity = self.table_client.get_entity(
                partition_key=category, row_key=faq_id
            )
            return FAQEntry(
                question=entity["Question"],
                answer=entity["Answer"],
                category=entity["PartitionKey"],
                id=entity["RowKey"],
                clicks=entity["Clicks"],
            )
        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="FAQ not found.")

    def update_faq(self, category: str, faq_id: str, faq: FAQUpdate):
        """
        Update an existing FAQ by category (PartitionKey) and ID (RowKey).
        If the category is updated, create a new entity in the new category,
        delete the old entity, and update the relevant fields.
        """
        try:
            # Fetch the existing entity from the database
            entity = self.table_client.get_entity(
                partition_key=category, row_key=faq_id
            )

            # Handle category update
            if faq.category and faq.category != category:
                # Copy the existing entity to a new PartitionKey
                new_entity = entity.copy()
                new_entity["PartitionKey"] = faq.category
                new_entity["RowKey"] = faq_id

                # Update specified fields
                if faq.question:
                    new_entity["Question"] = faq.question
                if faq.answer:
                    new_entity["Answer"] = faq.answer

                # Insert new entity and delete the old one
                self.table_client.create_entity(entity=new_entity)
                self.table_client.delete_entity(partition_key=category, row_key=faq_id)

                # Return the updated entity
                return FAQEntry(
                    question=new_entity.get("Question"),
                    answer=new_entity.get("Answer"),
                    category=new_entity.get("PartitionKey"),
                    id=new_entity.get("RowKey"),
                    clicks=new_entity.get(
                        "Clicks", 0
                    ),  # Default to 0 if clicks are missing
                )

            else:
                # Update only the specified fields in the existing entity
                if faq.question:
                    entity["Question"] = faq.question
                if faq.answer:
                    entity["Answer"] = faq.answer

                # Update the entity in Table Storage
                self.table_client.update_entity(entity=entity, mode=UpdateMode.REPLACE)

                # Return the updated entity
                return FAQEntry(
                    question=entity.get("Question"),
                    answer=entity.get("Answer"),
                    category=entity.get("PartitionKey"),
                    id=entity.get("RowKey"),
                    clicks=entity.get(
                        "Clicks", 0
                    ),  # Default to 0 if clicks are missing
                )

        except ResourceNotFoundError:
            raise HTTPException(status_code=404, detail="FAQ not found.")

        except Exception:
            raise HTTPException(status_code=500, detail="Internal Server Error.")

    def delete_faq(self, category: str, faq_id: str):
        """
        Delete an FAQ by category (PartitionKey) and ID (RowKey).
        Returns whether the deletion was successful or provides an error message.
        """
        try:
            # Verify if the entity exists before attempting deletion
            self.table_client.get_entity(partition_key=category, row_key=faq_id)

            # Proceed with deletion if the entity exists
            self.table_client.delete_entity(partition_key=category, row_key=faq_id)
            return {
                "success": True,
                "message": f"FAQ with ID '{faq_id}' successfully deleted from category '{category}'.",
            }

        except ResourceNotFoundError:
            # Handle case where the entity does not exist
            return {
                "success": False,
                "message": f"FAQ with ID '{faq_id}' not found in category '{category}'.",
            }

        except Exception as e:
            # Handle unexpected errors
            return {
                "success": False,
                "message": f"An unexpected error occurred while trying to delete the FAQ: {str(e)}",
            }

    def increment_clicks(self, category: str, faq_id: str):
        entity = self.table_client.get_entity(partition_key=category, row_key=faq_id)
        entity["Clicks"] = entity.get("Clicks", 0) + 1
        self.table_client.update_entity(entity, mode=UpdateMode.REPLACE)
        return {
            "detail": "Clicks incremented successfully.",
            "new_clicks": entity["Clicks"],
        }
