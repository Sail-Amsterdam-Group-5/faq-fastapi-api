from fastapi import HTTPException
from repositories.faq_repository import FAQRepository
from models.faq_models import FAQEntry, FAQUpdate
from azure.core.exceptions import ResourceExistsError, AzureError, ResourceNotFoundError
from typing import Optional
from errors import DatabaseError
import logging


class FAQService:
    def __init__(self, repository: FAQRepository):
        self.repository = repository
        self.logger = logging.getLogger(__name__)

    def create_faq_entry(self, faq: FAQEntry):
        """
        Service method to create a new FAQ entry, calls the repository function.
        Handles exceptions and returns a structured response.
        """
        try:
            # Call the repository to create the FAQ entry
            row_key, faq_entity = self.repository.create_faq_entry(faq)
            return {
                "message": "FAQ entry created successfully",
                "data": {
                    "id": row_key,
                    "question": faq_entity["Question"],
                    "answer": faq_entity["Answer"],
                    "category": faq_entity["PartitionKey"],
                },
            }

        except ResourceExistsError as e:
            # Handle conflict if FAQ entry already exists
            self.logger.error(f"Conflict while creating FAQ entry: {str(e)}")
            raise HTTPException(status_code=409, detail="FAQ entry already exists")

    def get_faqs_by_category(self, category: Optional[str] = None):
        """
        Retrieves FAQs from Azure Table Storage by category.
        Logs the process and handles any exceptions.
        """
        try:
            faqs = self.repository.get_faqs_by_category(category)

            # If no FAQs are found, raise a 404 error
            if not faqs:
                raise HTTPException(
                    status_code=404, detail="No FAQs found for the specified category."
                )

            return faqs

        except AzureError as e:
            # Custom error when there is a database-related issue
            self.logger.error(
                f"Error fetching FAQs from database: {str(e)}", exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail="Internal server error occurred while fetching FAQs.",
            )

    def get_faq_by_id(self, category: str, faq_id: str):
        try:
            # Call the repository method to retrieve the FAQ entry
            faq_entry = self.repository.get_faq_by_id(category, faq_id)
            return faq_entry

        except ResourceNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="No FAQ with the provided id and cetegory exists.",
            )

    def update_faq(self, category: str, faq_id: str, faq: FAQUpdate):
        try:
            # Call the repository method to update the FAQ entry
            updated_faq = self.repository.update_faq(category, faq_id, faq)
            return updated_faq

        except ResourceNotFoundError:
            # If the FAQ is not found, throw a 404 error
            raise HTTPException(status_code=404, detail="FAQ entry not found.")

        except DatabaseError as e:
            # If there is a database-related error (e.g., Azure error), throw a 500 error
            raise HTTPException(
                status_code=500, detail=f"Database error occurred: {e.message}"
            )

    def delete_faq(self, category: str, faq_id: str):
        """
        Calls the repository to delete an FAQ.
        Raises exceptions for failure or returns a success message.
        """
        result = self.repository.delete_faq(category, faq_id)

        if not result["success"]:
            if "not found" in result["message"].lower():
                raise HTTPException(status_code=404, detail=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])

        return {"message": result["message"]}

    def increment_clicks(self, category: str, faq_id: str):
        """
        Service method to increment the click count for a specific FAQ.
        Calls the repository method to handle the actual update.
        """
        try:
            # Call the repository method to increment clicks
            new_clicks = self.repository.increment_clicks(category, faq_id)

            return {
                "detail": "Clicks incremented successfully.",
                "new_clicks": new_clicks,
            }

        except ResourceNotFoundError:
            # If the FAQ entry is not found, raise a 404 error
            raise HTTPException(
                status_code=404, detail=f"FAQ entry with ID {faq_id} not found."
            )

        except AzureError:
            # If a more general Azure error occurs, raise a 500 error
            raise HTTPException(
                status_code=500,
                detail="Error interacting with Azure Table Storage database.",
            )
