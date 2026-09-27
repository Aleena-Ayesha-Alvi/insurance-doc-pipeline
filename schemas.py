# Reference schema for the per-document JSON written to outputs/
from pydantic import BaseModel
from typing import Dict, Optional


class ExtractedField(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0
    validation_passed: bool = False


class DocumentResult(BaseModel):
    document_name: str
    document_type: str
    detected_label: Optional[str] = None
    is_handwritten: bool
    ocr_text: str = ""
    extracted_data: Dict[str, ExtractedField]
