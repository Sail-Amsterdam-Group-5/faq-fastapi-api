from pydantic import BaseModel, Field
from typing import Optional


class FAQEntry(BaseModel):
    question: str = Field(..., min_length=5, max_length=500)
    answer: str = Field(..., min_length=1, max_length=1000)
    category: str = Field(..., min_length=1, max_length=100)
    id: Optional[str] = Field(None)
    clicks: Optional[int] = Field(0)


class FAQUpdate(BaseModel):
    question: Optional[str] = Field(None, min_length=5, max_length=500)
    answer: Optional[str] = Field(None, min_length=1, max_length=1000)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
