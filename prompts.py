FIELD_REQUIREMENTS = {
    "Aadhaar Card": [
        "Aadhaar Number",
        "Full Name",
        "Date of Birth",
        "Address"
    ],

    "PAN Card": [
        "PAN Number",
        "Full Name",
        "Father's Name",
        "Date of Birth"
    ],

    "Driving Licence": [
        "DL Number",
        "Name",
        "Date of Issue",
        "Valid Till Date"
    ],

    "Passport": [
        "Passport Number",
        "Date of Birth",
        "Date of Expiry",
        "MRZ Line 2"
    ],

    "NACH / ECS Mandate": [
        "Bank Account Number",
        "IFSC Code",
        "Bank Name",
        "Amount",
        "Frequency"
    ],

    "FATCA Annexure Form": [
        "Policy Number",
        "TIN / PAN",
        "Father's Name",
        "Place of Birth",
        "Nationality"
    ],

    "Benefit Illustration Declaration": [
        "Application Number",
        "Policyholder Name",
        "Date",
        "Place"
    ],

    "Moral Hazard Questionnaire": [
        "Application Number",
        "Name of Life Assured",
        "Nominee Relationship",
        "Date",
        "Place"
    ],

    "Multiple Policies Consent Form": [
        "Proposer Name",
        "Reason for Multiple Policies",
        "Date",
        "Place"
    ],

    "Suitability Profiler Declaration": [
        "Application Number",
        "Name of Life Assured",
        "Name of Agent/SP",
        "Date",
        "Place"
    ]
}


CLASSIFICATION_PROMPT = """
You are an insurance document classifier.

You MUST classify the document into EXACTLY ONE of these document types:

- Aadhaar Card
- PAN Card
- Driving Licence
- Passport
- NACH / ECS Mandate
- FATCA Annexure Form
- Benefit Illustration Declaration
- Moral Hazard Questionnaire
- Multiple Policies Consent Form
- Suitability Profiler Declaration

Return ONLY valid JSON.

{
  "document_type": "Aadhaar Card",
  "is_handwritten": false
}
"""


EXTRACTION_PROMPT = """
You are an insurance document extraction system.

Document Type:
{document_type}

Required Fields:
{required_fields}

OCR Text:
{ocr_text}

Instructions:

1. Extract ONLY the listed required fields.
2. Never invent values.
3. Use null when unavailable.
4. Confidence must be between 0 and 1.
5. Lower confidence when handwriting is unclear.
6. Lower confidence when OCR text is corrupted.
7. Return ONLY JSON.

Output Example:

{{
  "field_name": {{
    "value": "...",
    "confidence": 0.90
  }}
}}
"""