import os
import re
import json
from pathlib import Path
from datetime import datetime
from functools import lru_cache

import pymupdf
import easyocr

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from prompts import (
    CLASSIFICATION_PROMPT,
    EXTRACTION_PROMPT,
    FIELD_REQUIREMENTS
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw_documents"
OUTPUT_DIR = BASE_DIR / "outputs"
REVIEW_REPORT_NAME = "human_review_flagging_report.json"

SUPPORTED_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf"
)

CONFIDENCE_THRESHOLD = 0.80

ALLOWED_TYPES = [
    "Aadhaar Card",
    "PAN Card",
    "Driving Licence",
    "Passport",
    "NACH / ECS Mandate",
    "FATCA Annexure Form",
    "Benefit Illustration Declaration",
    "Moral Hazard Questionnaire",
    "Multiple Policies Consent Form",
    "Suitability Profiler Declaration"
]

UNKNOWN_TYPE = "Unknown"

# Government ID cards are always printed; only forms carry handwritten entries
PRINTED_TYPES = {
    "Aadhaar Card",
    "PAN Card",
    "Driving Licence",
    "Passport"
}

# Placeholder strings the LLM sometimes returns instead of a real null
EMPTY_VALUES = {
    "",
    "null",
    "none",
    "n/a",
    "na",
    "-"
}


# ---------------------------------------------------
# MODELS (created lazily so the module can be imported cheaply)
# ---------------------------------------------------

@lru_cache(maxsize=1)
def get_reader():

    return easyocr.Reader(
        ["en"],
        gpu=False
    )


@lru_cache(maxsize=1)
def get_llm():

    # LLM served via AI Pipe (OpenAI-compatible proxy)
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        base_url=os.getenv("LLM_BASE_URL", "https://aipipe.org/openai/v1"),
        api_key=os.getenv("AI_PIPE_KEY"),
        temperature=0
    )


# ---------------------------------------------------
# OCR
# ---------------------------------------------------

def pdf_to_text(pdf_path):

    full_text = ""

    doc = pymupdf.open(pdf_path)

    for page in doc:

        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))

        img_bytes = pix.tobytes("png")

        result = get_reader().readtext(img_bytes)

        for item in result:
            full_text += item[1] + "\n"

    return full_text


def image_to_text(image_path):

    result = get_reader().readtext(str(image_path))

    text = "\n".join(
        item[1]
        for item in result
    )

    return text


def extract_text(file_path):

    suffix = Path(file_path).suffix.lower()

    if suffix == ".pdf":
        return pdf_to_text(str(file_path))

    return image_to_text(file_path)


# ---------------------------------------------------
# LLM HELPERS
# ---------------------------------------------------

def parse_llm_json(content):

    content = content.strip()

    content = content.replace("```json", "")
    content = content.replace("```", "")
    content = content.strip()

    return json.loads(content)


# ---------------------------------------------------
# CLASSIFICATION
# ---------------------------------------------------

def classify_document(text):

    response = get_llm().invoke(
        f"{CLASSIFICATION_PROMPT}\n\n"
        f"OCR Text:\n<<<\n{text}\n>>>"
    )

    result = parse_llm_json(response.content)

    document_type = result.get("document_type")

    # A detected title that is literally a supported type name is authoritative
    label = (result.get("detected_label") or "").strip().lower()
    exact_match = next(
        (t for t in ALLOWED_TYPES if t.lower() == label),
        None
    )

    if exact_match:
        document_type = exact_match
        result["document_type"] = exact_match

    elif result.get("matches_supported_type") is False:
        document_type = UNKNOWN_TYPE
        result["document_type"] = UNKNOWN_TYPE

    if document_type != UNKNOWN_TYPE and document_type not in ALLOWED_TYPES:

        print(
            f"Unsupported document type returned: "
            f"{document_type}"
        )

        result["detected_label"] = (
            result.get("detected_label") or document_type
        )
        result["document_type"] = UNKNOWN_TYPE

    return result


# ---------------------------------------------------
# EXTRACTION
# ---------------------------------------------------

def extract_fields(
    document_type,
    text
):

    required_fields = FIELD_REQUIREMENTS.get(
        document_type,
        []
    )

    prompt = EXTRACTION_PROMPT.format(
        document_type=document_type,
        required_fields=required_fields,
        ocr_text=text
    )

    response = get_llm().invoke(prompt)

    try:
        extracted = parse_llm_json(response.content)

    except Exception:

        print(
            f"JSON parse failed "
            f"for {document_type}"
        )

        return {}

    # Normalise every field to {"value": ..., "confidence": ...}
    normalised = {}

    for field_name, field_data in extracted.items():

        if not isinstance(field_data, dict):
            field_data = {
                "value": field_data,
                "confidence": 0.5
            }

        value = field_data.get("value")

        if isinstance(value, str) and value.strip().lower() in EMPTY_VALUES:
            field_data["value"] = None

        normalised[field_name] = field_data

    return normalised


# ---------------------------------------------------
# VALIDATION
# ---------------------------------------------------

AADHAAR_REGEX = r"^\d{12}$"
PAN_REGEX = r"^[A-Z]{5}[0-9]{4}[A-Z]$"
PASSPORT_REGEX = r"^[A-Z][0-9]{7}$"
IFSC_REGEX = r"^[A-Z]{4}0[A-Z0-9]{6}$"

# Keys are field names normalised to snake_case (e.g. "Aadhaar Number" -> "aadhaar_number")
FORMAT_VALIDATORS = {
    "aadhaar_number": AADHAAR_REGEX,
    "pan_number": PAN_REGEX,
    "passport_number": PASSPORT_REGEX,
    "ifsc_code": IFSC_REGEX
}

DATE_FIELDS = [
    "date",
    "date_of_birth",
    "date_of_issue",
    "date_of_expiry",
    "valid_till_date"
]

DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y"
]


def normalise_field_name(field_name):

    return re.sub(
        r"[^a-z0-9]+",
        "_",
        field_name.lower()
    ).strip("_")


def validate_field(field_name, value):

    if value is None:
        return False

    value = str(value).replace(" ", "")

    if not value:
        return False

    key = normalise_field_name(field_name)

    if key in FORMAT_VALIDATORS:
        return bool(re.match(FORMAT_VALIDATORS[key], value.upper()))

    if key in DATE_FIELDS:
        return validate_date(value)

    return True


def validate_date(value):

    if value is None:
        return False

    for date_format in DATE_FORMATS:

        try:
            datetime.strptime(
                value,
                date_format
            )
            return True

        except ValueError:
            continue

    return False


# ---------------------------------------------------
# CONFIDENCE
# ---------------------------------------------------

def update_confidence(
    extracted_data,
    is_handwritten
):

    for field_name, field_data in extracted_data.items():

        try:
            confidence = float(
                field_data.get("confidence", 0.5)
            )
        except (TypeError, ValueError):
            confidence = 0.5

        value = field_data.get("value")

        validation_passed = validate_field(
            field_name,
            value
        )

        if validation_passed:
            confidence += 0.15
        else:
            confidence -= 0.30

        if is_handwritten:
            confidence -= 0.10

        confidence = max(
            0.0,
            min(confidence, 1.0)
        )

        field_data["confidence"] = round(
            confidence,
            2
        )

        field_data[
            "validation_passed"
        ] = validation_passed

    return extracted_data


# ---------------------------------------------------
# REVIEW REPORT
# ---------------------------------------------------

def create_review_items(
    filename,
    document_type,
    extracted_data
):

    items = []

    for field_name, field_data in extracted_data.items():

        confidence = field_data.get(
            "confidence",
            0
        )

        if confidence < CONFIDENCE_THRESHOLD:

            if not field_data.get("validation_passed", True):
                reason = "Below confidence threshold (validation failed)"
            else:
                reason = "Below confidence threshold"

            items.append(
                {
                    "document": filename,
                    "document_type": document_type,
                    "field": field_name,
                    "value": field_data.get("value"),
                    "confidence": confidence,
                    "reason": reason
                }
            )

    return items


# ---------------------------------------------------
# SINGLE DOCUMENT
# ---------------------------------------------------

def process_document(path, filename=None, ocr_text=None):
    """
    Runs OCR, classification, extraction, validation and confidence
    scoring for one document. Returns (output, review_items).
    Pass ocr_text to skip OCR and reuse previously extracted text.
    """

    filename = filename or Path(path).name

    text = ocr_text if ocr_text is not None else extract_text(path)

    classification = classify_document(
        text
    )

    document_type = classification.get(
        "document_type",
        UNKNOWN_TYPE
    )

    detected_label = classification.get(
        "detected_label"
    )

    is_handwritten = classification.get(
        "is_handwritten",
        True
    )

    if document_type in PRINTED_TYPES:
        is_handwritten = False

    if document_type == UNKNOWN_TYPE:

        # No field schema exists, so skip extraction and
        # route the whole document to a human for classification
        print(
            f"Unknown document type "
            f"(looks like: {detected_label})"
        )

        extracted = {}

        review_items = [
            {
                "document": filename,
                "document_type": UNKNOWN_TYPE,
                "field": "DOCUMENT_TYPE",
                "value": detected_label,
                "confidence": 0,
                "reason": "Unrecognised document type - manual classification required"
            }
        ]

    else:

        extracted = extract_fields(
            document_type,
            text
        )

        extracted = update_confidence(
            extracted,
            is_handwritten
        )

        review_items = create_review_items(
            filename,
            document_type,
            extracted
        )

    output = {
        "document_name": filename,
        "document_type": document_type,
        "detected_label": detected_label,
        "is_handwritten": is_handwritten,
        "ocr_text": text,
        "extracted_data": extracted
    }

    return output, review_items


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

def load_cached_ocr(filename):

    cached = OUTPUT_DIR / f"{Path(filename).stem}.json"

    if not cached.exists():
        return None

    with open(cached, encoding="utf-8") as f:
        return json.load(f).get("ocr_text")


def main(reuse_ocr=False):

    OUTPUT_DIR.mkdir(exist_ok=True)

    review_report = []

    files = sorted(
        f for f in os.listdir(RAW_DIR)
        if f.lower().endswith(SUPPORTED_EXTENSIONS)
    )

    for filename in files:

        try:

            print(
                f"Processing {filename}"
            )

            output, review_items = process_document(
                RAW_DIR / filename,
                ocr_text=load_cached_ocr(filename) if reuse_ocr else None
            )

            review_report.extend(
                review_items
            )

            output_file = OUTPUT_DIR / f"{Path(filename).stem}.json"

            with open(
                output_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    output,
                    f,
                    indent=2
                )

        except Exception as e:

            print(
                f"Failed: {filename}"
            )

            print(e)

            review_report.append(
                {
                    "document": filename,
                    "document_type": "UNKNOWN",
                    "field": "DOCUMENT_LEVEL_FAILURE",
                    "value": None,
                    "confidence": 0,
                    "reason": str(e)
                }
            )

    with open(
        OUTPUT_DIR / REVIEW_REPORT_NAME,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            review_report,
            f,
            indent=2
        )

    print("Pipeline Complete")


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(description="Insurance document processing pipeline")
    parser.add_argument(
        "--reuse-ocr",
        action="store_true",
        help="Reuse OCR text saved in outputs/ and re-run only the LLM stages"
    )

    main(reuse_ocr=parser.parse_args().reuse_ocr)
