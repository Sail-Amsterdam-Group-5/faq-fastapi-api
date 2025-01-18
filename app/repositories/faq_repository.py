from azure.data.tables import TableServiceClient, TableEntity, UpdateMode
from azure.core.exceptions import ResourceNotFoundError
from models.faq_models import FAQEntry, FAQUpdate
from fastapi import HTTPException
import uuid
import os
from typing import Optional

connection_string = os.getenv("FAQ_AZURE_CONN_STRING", "MOCK_CONNECTION_STRING")
TABLE_NAME = "faqs"


class FAQRepository:
    def __init__(self):
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
        entity = self.table_client.get_entity(partition_key=category, row_key=faq_id)
        if faq.question:
            entity["Question"] = faq.question
        if faq.answer:
            entity["Answer"] = faq.answer
        self.table_client.update_entity(entity, mode=UpdateMode.REPLACE)
        return FAQEntry(**entity)

    def delete_faq(self, category: str, faq_id: str):
        self.table_client.delete_entity(partition_key=category, row_key=faq_id)

    def increment_clicks(self, category: str, faq_id: str):
        entity = self.table_client.get_entity(partition_key=category, row_key=faq_id)
        entity["Clicks"] = entity.get("Clicks", 0) + 1
        self.table_client.update_entity(entity, mode=UpdateMode.REPLACE)
        return {
            "detail": "Clicks incremented successfully.",
            "new_clicks": entity["Clicks"],
        }
