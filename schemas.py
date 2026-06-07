from pydantic import BaseModel
from typing import Dict, Optional


class ExtractedField(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0
    validation_passed: bool = False
    review_reason: Optional[str] = None


class DocumentResult(BaseModel):
    document_name: str
    document_type: str
    is_handwritten: bool
    extracted_data: Dict[str, ExtractedField]