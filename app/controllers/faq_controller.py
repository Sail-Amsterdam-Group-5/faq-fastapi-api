from fastapi import APIRouter, Depends, status
from typing import List, Optional
from models.faq_models import FAQEntry, FAQUpdate
from services.faq_service import FAQService
from repositories.faq_repository import FAQRepository

router = APIRouter()


# Dependency for creating FAQService with injected FAQRepository
def get_faq_service(repository: FAQRepository = Depends(FAQRepository)) -> FAQService:
    return FAQService(repository)


@router.post("/faqs", status_code=201)
async def create_faq_entry(
    faq: FAQEntry, faq_service: FAQService = Depends(get_faq_service)
):
    return faq_service.create_faq_entry(faq)


@router.get("/faqs", response_model=List[FAQEntry])
async def get_faqs_by_category(
    category: Optional[str] = None, faq_service: FAQService = Depends(get_faq_service)
):
    return faq_service.get_faqs_by_category(category)


@router.get("/faqs/{category}/{faq_id}", response_model=FAQEntry)
async def get_faq_by_id(
    category: str, faq_id: str, faq_service: FAQService = Depends(get_faq_service)
):
    return faq_service.get_faq_by_id(category, faq_id)


@router.put("/faqs/{category}/{faq_id}", response_model=FAQEntry)
async def update_faq(
    category: str,
    faq_id: str,
    faq: FAQUpdate,
    faq_service: FAQService = Depends(get_faq_service),
):
    return faq_service.update_faq(category, faq_id, faq)


@router.delete("/faqs/{category}/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(
    category: str, faq_id: str, faq_service: FAQService = Depends(get_faq_service)
):
    return faq_service.delete_faq(category, faq_id)


@router.post("/faqs/{category}/{faq_id}/click")
async def increment_clicks(
    category: str, faq_id: str, faq_service: FAQService = Depends(get_faq_service)
):
    return faq_service.increment_clicks(category, faq_id)
