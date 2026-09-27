# 📄 Insurance Document Processing Pipeline

## Overview

A document processing pipeline that classifies insurance and identity documents, extracts required fields, assigns field-level confidence scores, and flags low-confidence results for human review.

The solution processes both image documents (PNG, JPG, JPEG) and PDF documents, and can be used as a batch script or through a Streamlit web app.

Pipeline flow:

Document → OCR → Document Classification → Field Extraction → Validation → Confidence Scoring → Human Review Flagging

## 🚀 Live Demo

https://insurance-doc-pipeline-dxm9poapjqgappokbeg2qxi.streamlit.app/

---

## ⚙️ Setup & Run

Requires Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

`requirements.txt` pulls the CPU-only build of PyTorch (for EasyOCR), which keeps the install small.

Copy `.env.example` to `.env` and add your token:

```env
AI_PIPE_KEY=your_aipipe_token
# Optional overrides
# LLM_MODEL=gpt-4o-mini
# LLM_BASE_URL=https://aipipe.org/openai/v1
```

Get a token at [aipipe.org](https://aipipe.org). The LLM is called through AI Pipe's OpenAI-compatible endpoint, so any OpenAI-compatible provider works by changing `LLM_BASE_URL` and `LLM_MODEL`.

### Web App

```bash
streamlit run app.py
```

* **Process a Document**: upload an image/PDF (or pick a sample) and run the full pipeline live.
* **Sample Results**: browse the precomputed results for the 12 sample documents and the full human review report (no API calls).

### Batch Pipeline

```bash
python pipeline.py              # OCR + LLM for every file in raw_documents/
python pipeline.py --reuse-ocr  # re-run only the LLM stages using OCR text saved in outputs/
```

Results are written to `outputs/`. EasyOCR downloads its detection and recognition models on the first run; OCR runs on CPU and takes roughly 30–60 seconds per document. `--reuse-ocr` is useful when iterating on prompts, since it skips OCR entirely.

---

## ☁️ Deploy to Streamlit Cloud

1. Push this repository to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), click **Create app** and select the repository, branch `main` and main file `app.py`.
3. Under **Advanced settings**, choose Python **3.12** and add the secret:
   ```toml
   AI_PIPE_KEY = "your_aipipe_token"
   ```
4. Click **Deploy**. The first boot takes a few minutes while PyTorch installs, and the first live run downloads the EasyOCR models (~100 MB).

The **Sample Results** tab works without any API calls, so reviewers can explore the outputs even if the API budget is exhausted.

---

## Project Structure

```text
insurance-doc-pipeline/
│
├── app.py                  # Streamlit web app
├── pipeline.py             # OCR, classification, extraction, validation, review flagging
├── prompts.py              # Classification/extraction prompts and field requirements
├── schemas.py              # Pydantic schemas for the output format
├── requirements.txt
├── .env.example
│
├── raw_documents/          # 12 sample documents
└── outputs/                # One JSON per document + human_review_flagging_report.json
```

---

## Document Classification

Document type classification is performed using GPT-4o mini via AI Pipe.

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
- Unknown

Each supported type is given a one-line description in the prompt, and the OCR text is passed inside clear delimiters.

### Unknown Documents

The classifier follows three explicit steps:

1. Identify the document's own title or purpose from the OCR text (`detected_label`).
2. Decide whether that title is the **same kind of document** as a supported type (`matches_supported_type`). Shared fields (name, date, place, reason, policy number) or shared vocabulary do not count.
3. If it does not match, the type **must** be `Unknown`.

The pipeline enforces these decisions in code:

* `matches_supported_type: false` always results in `Unknown`.
* A `detected_label` that is literally a supported type name (e.g. "Moral Hazard Questionnaire") always maps to that type.
* Any label outside the supported list is routed to `Unknown`.

Unknown documents:

* Skip field extraction, since no field schema exists for them and the model would otherwise invent fields
* Are added to the Human Review Report as a single `DOCUMENT_TYPE` item for manual classification

```json
{
  "document": "Assignment Ashok.pdf",
  "document_type": "Unknown",
  "field": "DOCUMENT_TYPE",
  "value": "ASSIGNMENT REQUEST FORM",
  "confidence": 0,
  "reason": "Unrecognised document type - manual classification required"
}
```

In the sample set, the 10 supported types map one-to-one onto 10 documents, and the two extra documents (an *Assignment Request Form* and a *Customer Declaration – Application/Proposal Form*) are flagged as Unknown. Previously they were forced into unrelated types such as Moral Hazard Questionnaire or Benefit Illustration Declaration. Classification was verified to be stable across three consecutive runs.

---

# 1. Extraction Output

For every processed document, the system generates a structured JSON file containing:

* Document name
* Document type
* Detected label (the document's title as identified by the classifier)
* Handwritten/Printed indicator
* OCR text
* Extracted fields
* Confidence score per field
* Validation status per field

Example output structure (`outputs/ECS.json`, abbreviated):

```json
{
  "document_name": "ECS.jpeg",
  "document_type": "NACH / ECS Mandate",
  "detected_label": "NACH MANDATE INSTRUCTION",
  "is_handwritten": true,
  "ocr_text": "...",
  "extracted_data": {
    "Bank Name": {
      "value": "HDFC",
      "confidence": 0.95,
      "validation_passed": true
    },
    "IFSC Code": {
      "value": "SBICNCCISB",
      "confidence": 0.2,
      "validation_passed": false
    }
  }
}
```

---

# 2. Confidence Scoring Methodology

Field-level confidence scores are generated instead of a single document confidence score.

Initial confidence is obtained from the LLM extraction response. The extraction prompt defines an explicit calibration scale so the model does not rate garbled OCR output as certain:

| Initial confidence | Meaning |
|---|---|
| 0.90 – 1.00 | Clean, fully legible value in the expected format |
| 0.60 – 0.80 | Readable but with minor OCR noise, or uncertain spelling |
| 0.30 – 0.50 | Garbled value (e.g. "Kephew", "Lndean", "L500131olbob") or partial value ("West B", "26/2021") |
| 0.00 – 0.20 | A guess, or the value could not be located |

The confidence score is then adjusted using deterministic rules:

* Validation passed → +0.15 confidence
* Validation failed → −0.30 confidence
* Handwritten document → −0.10 confidence adjustment

Final confidence score is clipped between 0.0 and 1.0.

This approach produces confidence values that are grounded in validation outcomes rather than relying solely on LLM self-assessment.

---

# 3. Validation Rules

Field names are normalised (e.g. `Aadhaar Number` → `aadhaar_number`) before the rules are applied. The following deterministic validation rules are implemented:

## Aadhaar Number

Pattern: 12 numeric digits (spaces ignored)

Example: 1234 5678 9012

## PAN Number

Pattern: AAAAA9999A

Example: ABCDE1234F

## Passport Number

Pattern: A1234567

## IFSC Code

Pattern: AAAA0XXXXXX

Example: SBIN0027112

## Date Fields

Supported formats: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY

Examples: 15/06/2021, 14-06-2041

## Empty Values

Placeholder strings returned by the LLM (`"null"`, `"None"`, `"N/A"`, `"-"`) are converted to a real `null` and fail validation.

> **Fix note:** in the original version the ID-number rules compared against snake_case keys (`aadhaar_number`) while the extracted fields used display names (`Aadhaar Number`), so Aadhaar, PAN, Passport and IFSC validation never ran. Field-name normalisation fixes this.

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

`outputs/human_review_flagging_report.json`

The report contains:

* Document Name
* Document Type
* Field Name
* Extracted Value
* Confidence Score
* Review Reason (including whether validation failed)

Example:

```json
{
  "document": "Fatca.jpeg",
  "document_type": "FATCA Annexure Form",
  "field": "Nationality",
  "value": "Lndean",
  "confidence": 0.35,
  "reason": "Below confidence threshold"
}
```

---

# 6. Handwritten Text Handling

Handwritten content is treated differently from printed content.

Approach:

1. OCR extraction performed using EasyOCR.
2. The classifier flags forms whose filled-in values appear handwritten (garbled or misspelt values, letters mixed into numbers, broken fragments next to printed labels).
3. Government ID cards (Aadhaar, PAN, Driving Licence, Passport) are always treated as printed. This deterministic rule prevents printed cards from receiving the handwriting penalty.
4. Documents classified as handwritten receive an additional confidence penalty.
5. Missing handwritten values are automatically routed to human review.
6. Low-confidence handwritten fields are never forced into a final result.

Examples of handwritten fields:

* IFSC Code
* TIN / PAN
* Place of Birth
* Application Number
* Date fields
* Place names

This reduces the risk of silently accepting incorrect handwritten values.

---

# 7. Failure Cases Observed

## ECS Mandate – IFSC Code

Expected Value:

SBIN0027112

Issue:

The IFSC code is visually readable but OCR produced a noisy value (`SBICNCCISB`).

Root Cause:

OCR merged adjacent handwritten and printed regions into a noisy text segment, preventing correct field isolation.

Result:

IFSC validation failed (confidence 0.2) and the field was routed to Human Review.

---

## Place Names and Nationality

Examples:

* West Bihar
* Indian

Issue:

OCR introduced character substitutions and spelling distortions.

Examples:

* WesdBeky, Wesl Bilnx Ran, JlesL Bibr
* Lndean

Result:

Confidence reduced (0.35) and fields flagged for review.

---

## Handwritten Dates

Examples:

* 26/202L
* 26luks

Issue:

Character ambiguity between letters and numbers.

Result:

Date validation failed and confidence dropped to 0.0.

---

## Remaining Limitation – Plausible Misreadings

OCR errors that still look like valid words (e.g. "Asbok" for "Ashok") can receive high confidence because neither the LLM nor the regex rules can tell they are wrong. Cross-checking names across documents belonging to the same applicant would catch these.

---

# 8. Technologies Used

OCR:

* EasyOCR

LLM:

* GPT-4o mini via AI Pipe (OpenAI-compatible API)

PDF Processing:

* PyMuPDF

PDF documents are converted into page images before OCR and extraction.

Validation:

* Regex-based deterministic validation

Interface:

* Streamlit

Output Format:

* Structured JSON

Review Workflow:

* Confidence-based human review routing

---

# Results Summary

Documents processed: 12 (10 supported types + 2 Unknown)

Fields extracted: 44

Human review items: 25

| Document | Type | Handwritten | Review Items |
|---|---|---|---|
| Aadhar.png | Aadhaar Card | No | 1 |
| ChatGPT Image …03_43_11 PM.png | Driving Licence | No | 0 |
| ChatGPT Image …03_52_54 PM.png | Passport | No | 0 |
| ID.png | PAN Card | No | 0 |
| ECS.jpeg | NACH / ECS Mandate | Yes | 4 |
| Fatca.jpeg | FATCA Annexure Form | Yes | 4 |
| Illustration.jpeg | Benefit Illustration Declaration | Yes | 3 |
| Moral.jpeg | Moral Hazard Questionnaire | Yes | 3 |
| split.jpeg | Multiple Policies Consent Form | Yes | 3 |
| suitability.jpeg | Suitability Profiler Declaration | Yes | 5 |
| Assignment Ashok.pdf | Unknown (Assignment Request Form) | Yes | 1 |
| Proposal Ashok.pdf | Unknown (Application/Proposal Form) | Yes | 1 |

Fields flagged for review:

- Noisy IFSC Code and bank account number in the ECS Mandate
- Missing or garbled handwritten dates
- Garbled handwritten place names and nationality
- Letter/digit confusion in application numbers
- Documents outside the supported categories (classified as Unknown)

The pipeline completed successfully without requiring manual intervention during processing.

# Conclusion

The implemented pipeline successfully performs:

* Document classification, including explicit handling of unsupported documents
* Structured field extraction
* Field-level confidence estimation
* Deterministic validation
* Human review routing

The system performs strongly on printed identity documents (all fields pass with full confidence) and provides a safe review workflow for uncertain handwritten insurance forms.
