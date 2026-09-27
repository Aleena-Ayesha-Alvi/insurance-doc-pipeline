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

- Aadhaar Card: UIDAI identity card with a 12-digit Aadhaar number
- PAN Card: Income Tax Department card with a 10-character PAN
- Driving Licence: licence to drive issued by a transport authority
- Passport: travel document with passport number and MRZ lines
- NACH / ECS Mandate: bank debit mandate with account number, IFSC and amount
- FATCA Annexure Form: FATCA / CRS tax residency declaration
- Benefit Illustration Declaration: declaration acknowledging the benefit illustration or proposal details of a policy
- Moral Hazard Questionnaire: questionnaire on moral hazard / insurable interest
- Multiple Policies Consent Form: consent or reason for holding multiple policies
- Suitability Profiler Declaration: customer suitability / needs analysis declaration
- Unknown: anything else

Steps:
1. Read the OCR text (it may be noisy) and identify the document's own title
   or purpose. Put it in "detected_label".
2. Decide whether that title/purpose is the SAME kind of document as one of
   the supported types and set "matches_supported_type" to true or false.
   Shared fields (name, date, place, reason, policy number, bank) or shared
   vocabulary do NOT make two forms the same kind of document. For example,
   an assignment, nomination, claim, loan or address-change form is not any
   of the supported types.
3. If "matches_supported_type" is false, "document_type" MUST be "Unknown".
   Do NOT force a document into the closest type; an unrecognised form must
   be flagged, not mislabelled.
4. Set "is_handwritten" to true if the filled-in values appear handwritten.
   Printed ID cards (Aadhaar, PAN, Driving Licence, Passport) are normally
   printed. On forms, handwriting shows up in OCR as misspelt or garbled
   filled-in values (e.g. "Asbok" for "Ashok"), letters mixed into numbers
   (e.g. "L500131olbob"), and broken fragments next to printed labels.

Return ONLY valid JSON in this format:

{
  "detected_label": "PAN Card",
  "matches_supported_type": true,
  "document_type": "PAN Card",
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
2. Never invent values. Copy the value as it appears in the OCR text.
3. Use null when unavailable.
4. Confidence must be between 0 and 1 and reflect how likely the value is
   EXACTLY correct, using this scale:
   - 0.90-1.00: clean, fully legible value in the expected format
     (e.g. "ABCDE1234F", "18/12/1979", "Mumbai").
   - 0.60-0.80: readable but with minor OCR noise, or a plausible value whose
     exact spelling is uncertain.
   - 0.30-0.50: garbled value (misspelt words such as "Kephew", "Lndean",
     "WesdBeky"; letters mixed into numbers such as "L500131olbob"; partial
     values such as "West B" or "26/2021").
   - 0.00-0.20: a guess, or the value could not be located.
5. Never give a garbled or partial value a confidence above 0.60.
6. Return ONLY JSON.

Output Example:

{{
  "field_name": {{
    "value": "...",
    "confidence": 0.90
  }}
}}
"""