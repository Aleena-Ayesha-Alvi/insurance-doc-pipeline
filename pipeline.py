import os
import io
import re
import json
from pathlib import Path
from datetime import datetime
import fitz
import easyocr

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from prompts import (
    CLASSIFICATION_PROMPT,
    EXTRACTION_PROMPT,
    FIELD_REQUIREMENTS
)

load_dotenv()

RAW_DIR = "raw_documents"
OUTPUT_DIR = "outputs"

CONFIDENCE_THRESHOLD = 0.80

os.makedirs(OUTPUT_DIR, exist_ok=True)

reader = easyocr.Reader(
    ["en"],
    gpu=False
)

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0
)

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

# ---------------------------------------------------
# OCR
# ---------------------------------------------------

def pdf_to_text(pdf_path):

    full_text = ""

    doc = fitz.open(pdf_path)

    for page in doc:

        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        img_bytes = pix.tobytes("png")

        result = reader.readtext(img_bytes)

        for item in result:
            full_text += item[1] + "\n"

    return full_text


def image_to_text(image_path):

    result = reader.readtext(image_path)

    text = "\n".join(
        item[1]
        for item in result
    )

    return text


def extract_text(file_path):

    suffix = Path(file_path).suffix.lower()

    if suffix == ".pdf":
        return pdf_to_text(file_path)

    return image_to_text(file_path)


# ---------------------------------------------------
# CLASSIFICATION
# ---------------------------------------------------

def classify_document(text):

    response = llm.invoke(
        f"{CLASSIFICATION_PROMPT}\n\n{text}"
    )

    content = response.content.strip()

    content = content.replace("```json", "")
    content = content.replace("```", "")
    content = content.strip()

    result = json.loads(content)

    if result["document_type"] not in ALLOWED_TYPES:

        print(
            f"Unknown document type detected: "
            f"{result['document_type']}"
        )

        result = {
            "document_type":
                "Benefit Illustration Declaration",
            "is_handwritten": True
        }

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

    response = llm.invoke(prompt)

    content = response.content.strip()

    content = content.replace(
        "```json",
        ""
    )

    content = content.replace(
        "```",
        ""
    )

    content = content.strip()

    try:
        return json.loads(content)

    except Exception:

        print(
            f"JSON parse failed "
            f"for {document_type}"
        )

        return {}


# ---------------------------------------------------
# VALIDATION
# ---------------------------------------------------

AADHAAR_REGEX = r"^\d{12}$"
PAN_REGEX = r"^[A-Z]{5}[0-9]{4}[A-Z]$"
PASSPORT_REGEX = r"^[A-Z][0-9]{7}$"
IFSC_REGEX = r"^[A-Z]{4}0[A-Z0-9]{6}$"


def validate_field(field_name, value):

    if value is None:
        return False

    value = str(value).replace(" ", "")

    if field_name == "aadhaar_number":
        return bool(re.match(AADHAAR_REGEX, value))

    if field_name == "pan_number":
        return bool(re.match(PAN_REGEX, value))

    if field_name == "passport_number":
        return bool(re.match(PASSPORT_REGEX, value))

    if field_name == "ifsc_code":
        return bool(re.match(IFSC_REGEX, value))
    
    DATE_FIELDS = [
    "Date",
    "Date of Birth",
    "Date of Issue",
    "Date of Expiry",
    "Valid Till Date"
    ]

    if field_name in DATE_FIELDS:
        return validate_date(value)

    return True

def validate_date(value):

    if value is None:
        return False

    try:
        datetime.strptime(
            value,
            "%d/%m/%Y"
        )
        return True

    except:
        return False
# ---------------------------------------------------
# CONFIDENCE
# ---------------------------------------------------

def update_confidence(
    extracted_data,
    is_handwritten
):

    for field_name, field_data in extracted_data.items():

        confidence = float(
            field_data.get(
                "confidence",
                0.5
            )
        )

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

            items.append(
                {
                    "document": filename,
                    "document_type": document_type,
                    "field": field_name,
                    "value": field_data.get("value"),
                    "confidence": confidence,
                    "reason": "Below confidence threshold"
                }
            )

    return items


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

def main():

    review_report = []

    files = [
        f for f in os.listdir(RAW_DIR)
        if f.lower().endswith(
            (
                ".png",
                ".jpg",
                ".jpeg",
                ".pdf"
            )
        )
    ]

    for filename in files:

        try:

            print(
                f"Processing {filename}"
            )

            path = os.path.join(
                RAW_DIR,
                filename
            )

            text = extract_text(path)

            classification = classify_document(
                text
            )

            document_type = classification.get(
                "document_type",
                "Benefit Illustration Declaration"
            )

            is_handwritten = classification.get(
                "is_handwritten",
                True
            )

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

            review_report.extend(
                review_items
            )

            output = {
            "document_name": filename,
            "document_type": document_type,
            "is_handwritten": is_handwritten,
            "ocr_text": text,
            "extracted_data": extracted
            }

            output_file = os.path.join(
                OUTPUT_DIR,
                f"{Path(filename).stem}.json"
            )

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
        os.path.join(
            OUTPUT_DIR,
            "human_review_flagging_report.json"
        ),
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
    main()