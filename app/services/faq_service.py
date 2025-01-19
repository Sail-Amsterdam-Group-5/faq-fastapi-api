from fastapi import HTTPException
from repositories.faq_repository import FAQRepository
from models.faq_models import FAQEntry, FAQUpdate
from typing import Optional


class FAQService:
    def __init__(self, repository: FAQRepository):
        self.repository = repository

    def create_faq_entry(self, faq: FAQEntry):
        return self.repository.create_faq_entry(faq)

    def get_faqs_by_category(self, category: Optional[str] = None):
        faqs = self.repository.get_faqs_by_category(category)
        if not faqs:
            raise HTTPException(status_code=404, detail="No FAQs found.")
        return faqs

    def get_faq_by_id(self, category: str, faq_id: str):
        return self.repository.get_faq_by_id(category, faq_id)

    def update_faq(self, category: str, faq_id: str, faq: FAQUpdate):
        return self.repository.update_faq(category, faq_id, faq)

    def delete_faq(self, category: str, faq_id: str):
        self.repository.delete_faq(category, faq_id)
        return {"message": "FAQ deleted successfully."}

    def increment_clicks(self, category: str, faq_id: str):
        return self.repository.increment_clicks(category, faq_id)
