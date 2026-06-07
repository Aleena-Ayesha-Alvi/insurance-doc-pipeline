# Document Processing Pipeline – Assessment Submission

## Overview

A document processing pipeline was developed to classify insurance and identity documents, extract required fields, assign field-level confidence scores, and flag low-confidence results for human review.

The solution processes both image documents (PNG, JPG, JPEG) and PDF documents.

Pipeline flow:

Document → OCR → Document Classification → Field Extraction → Validation → Confidence Scoring → Human Review Flagging

---

## Document Classification

Document type classification is performed using the Llama 3.3 70B model.

The model receives OCR text extracted from the document and classifies it into one of the supported document categories:

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

# 1. Extraction Output

For every processed document, the system generates a structured JSON file containing:

* Document name
* Document type
* Handwritten/Printed indicator
* OCR text
* Extracted fields
* Confidence score per field
* Validation status per field

Example output structure:

```json
{
  "document_name": "ECS.jpeg",
  "document_type": "NACH / ECS Mandate",
  "is_handwritten": false,
  "ocr_text": "...",
  "extracted_data": {
    "Bank Account Number": {
      "value": "31004258912",
      "confidence": 1.0,
      "validation_passed": true
    },
    "IFSC Code": {
      "value": null,
      "confidence": 0.0,
      "validation_passed": false
    }
  }
}
```

---

# 2. Confidence Scoring Methodology

Field-level confidence scores were generated instead of assigning a single document confidence score.

Initial confidence is obtained from the LLM extraction response.

The confidence score is then adjusted using validation rules:

* Validation passed → +0.15 confidence
* Validation failed → −0.30 confidence
* Handwritten document → −0.10 confidence adjustment

Final confidence score is clipped between 0.0 and 1.0.

This approach produces confidence values that are grounded in validation outcomes rather than relying solely on LLM self-assessment.

---

# 3. Validation Rules

The following deterministic validation rules were implemented:

## Aadhaar Number

Pattern:

12 numeric digits

Example:

123456789012

---

## PAN Number

Pattern:

AAAAA9999A

Example:

ABCDE1234F

---

## Passport Number

Pattern:

A1234567

---

## IFSC Code

Pattern:

AAAA0XXXXXX

Example:

SBIN0027112

---

## Date Fields

Supported format:

DD/MM/YYYY

Examples:

15/06/2021

14/06/2041

---

# 4. Human Review Threshold

Selected threshold:

0.80

Fields with confidence below 0.80 are added to the Human Review Report.

Rationale:

* Handwritten forms naturally produce lower OCR quality.
* A threshold of 0.80 balances extraction accuracy and reviewer workload.
* Higher thresholds generated excessive false review requests.
* Lower thresholds allowed uncertain handwritten values to pass without review.

---

# 5. Human Review Report

A consolidated report is generated:

human_review_flagging_report.json

The report contains:

* Document Name
* Document Type
* Field Name
* Extracted Value
* Confidence Score
* Review Reason

Example:

```json
{
  "document": "Illustration.jpeg",
  "document_type": "Benefit Illustration Declaration",
  "field": "Date",
  "value": null,
  "confidence": 0.0,
  "reason": "Below confidence threshold"
}
```

---

# 6. Handwritten Text Handling

Handwritten content was treated differently from printed content.

Approach:

1. OCR extraction performed using EasyOCR.
2. Documents classified as handwritten received additional confidence penalties.
3. Missing handwritten values were automatically routed to human review.
4. Low-confidence handwritten fields were never forced into a final result.

Examples of handwritten fields:

* IFSC Code
* TIN / PAN
* Place of Birth
* Application Number
* Date fields
* Place names

This reduced the risk of silently accepting incorrect handwritten values.

---

# 7. Failure Cases Observed

## ECS Mandate – IFSC Code

Expected Value:

SBIN0027112

Issue:

The IFSC code was visually readable but was not extracted by the OCR pipeline.

Root Cause:

OCR merged adjacent handwritten and printed regions into a noisy text segment, preventing correct field isolation.

Result:

Field routed to Human Review.

---

## Place Names

Examples:

* West Bihar
* Place of Birth

Issue:

OCR introduced character substitutions and spelling distortions.

Examples:

* WesdBeky
* West B

Result:

Confidence reduced and fields flagged for review.

---

## Handwritten Dates

Examples:

* 26/202L
* 2 loy IoL

Issue:

Character ambiguity between letters and numbers.

Result:

Date validation failed and confidence decreased.

---

# 8. Technologies Used

OCR:

* EasyOCR

LLM:

* Llama 3.3 70B Versatile (Groq)

PDF Processing:
- PyMuPDF

PDF documents are converted into page images before OCR and extraction.

Validation:

* Regex-based deterministic validation

Output Format:

* Structured JSON

Review Workflow:

* Confidence-based human review routing

---
# Results Summary

Documents processed: 12

Outputs generated:
- Structured JSON per document
- Human review report

Fields flagged for review:
- Missing IFSC Code in ECS Mandate
- Low confidence handwritten dates
- Low confidence handwritten place names
- Missing handwritten values where extraction confidence was insufficient

The pipeline completed successfully without requiring manual intervention during processing.

# Conclusion

The implemented pipeline successfully performs:

* Document classification
* Structured field extraction
* Field-level confidence estimation
* Deterministic validation
* Human review routing

The system performs strongly on printed identity documents and provides a safe review workflow for uncertain handwritten insurance forms.
