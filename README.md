# 📄 Insurance Document Processing Pipeline

Upload a scanned insurance form or identity document and the pipeline reads it (OCR), works out what kind of document it is, extracts the required fields, checks them against validation rules, scores how confident it is in each value, and **flags anything uncertain for a human to review**. Documents it doesn't recognise are flagged as `Unknown` instead of being mislabelled.

**🚀 Live Demo:** https://insurance-doc-pipeline-dxm9poapjqgappokbeg2qxi.streamlit.app/

---

## 🧪 Try These on the Live App

### 📂 Sample Results tab (instant, no API cost)
Browse precomputed results for all 12 sample documents: the summary table, each document's extracted fields with confidence and validation status, its image, and the full human review report.

### 🔍 Process a Document tab (runs the full pipeline live)
Choose **Use a sample document**, pick one of these, and click **Run Pipeline**:

| Sample | Expected result |
|---|---|
| `Aadhar.png` | **Aadhaar Card**, printed. Aadhaar number `1234 5678 9012`, name, DOB `18/12/1979`; Aadhaar format check passes |
| `ID.png` | **PAN Card**, printed. PAN `ABCDE1234F` passes the PAN format check; **all fields pass** the 0.80 threshold |
| `ChatGPT Image May 2, 2026, 03_52_54 PM.png` | **Passport**. Passport number `X1234567`, DOB, expiry and MRZ line; all fields pass |
| `Fatca.jpeg` | **FATCA Annexure Form**, handwritten. Garbled values such as Nationality "Lndean" and Place of Birth "WesdBeky" are **flagged for review** |
| `ECS.jpeg` | **NACH / ECS Mandate**, handwritten. The noisy IFSC code fails the IFSC format check and is **flagged** |
| `Assignment Ashok.pdf` | **Unknown** (detected title: *Assignment Request Form*). Extraction is skipped and the document is sent for manual classification |

You can also choose **Upload a file** and try your own PNG, JPG or PDF. The first live run on a fresh deployment downloads the OCR models, so give it a minute. Multi-page PDFs take longer because every page is OCR'd.

---

## What It Does

It processes the documents an insurer receives with a policy application:

- **Identity documents:** Aadhaar Card, PAN Card, Driving Licence, Passport
- **Insurance forms:** NACH / ECS Mandate, FATCA Annexure, Benefit Illustration Declaration, Moral Hazard Questionnaire, Multiple Policies Consent Form, Suitability Profiler Declaration
- **Anything else** → `Unknown`, routed to a person

For every document it produces a structured JSON record (type, detected title, handwritten or printed, OCR text, and each field with value, confidence and validation status). It also maintains one consolidated **human review report** listing every field that needs a person to check it.

It can be used through the **Streamlit web app** or as a **batch script** over a folder of documents.

---

## How It Works

```text
Image / PDF
    │
    ▼
① OCR (EasyOCR; PDFs rendered page-by-page with PyMuPDF)
    │  raw text
    ▼
② Classification (LLM)
    │  detected title → matches a supported type? → document type + handwritten?
    │  no match ─────────────────────────────► Unknown → manual review
    ▼
③ Field extraction (LLM)
    │  required fields for that type, each with a calibrated confidence
    ▼
④ Validation (deterministic rules)
    │  Aadhaar / PAN / Passport / IFSC formats, dates, empty values
    ▼
⑤ Confidence scoring
    │  +0.15 valid · −0.30 invalid · −0.10 handwritten
    ▼
⑥ Human review flagging (confidence < 0.80)
    │
    ▼
JSON per document + human_review_flagging_report.json
```

**① OCR.** EasyOCR reads images directly. PDFs are rendered to images at 2× resolution with PyMuPDF and every page is read.

**② Classification.** The LLM receives the OCR text and follows three explicit steps. First it identifies the document's own title (`detected_label`). Then it decides whether that title is the **same kind of document** as a supported type (`matches_supported_type`); shared fields like name, date or policy number don't count. Finally it picks the type or `Unknown`. The code enforces this decision, so a document can never be forced into the closest type. Government ID cards are always treated as printed; for forms, the LLM decides whether the filled-in values are handwritten.

**③ Extraction.** Each document type has a fixed list of required fields (e.g. PAN Card → PAN Number, Full Name, Father's Name, Date of Birth). The LLM extracts only those fields and rates each value on an explicit scale, so garbled OCR output like "Kephew" or "L500131olbob" is not rated as certain.

**④–⑥ Validation, scoring and review.** Deterministic rules check formats and adjust the LLM's confidence. Any field below **0.80** goes into the human review report, along with every `Unknown` document.

The sections below document each stage in detail.

---

## Try It Locally

Requires Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt  # installs CPU-only PyTorch for EasyOCR
```

Copy `.env.example` to `.env` and add your [AI Pipe](https://aipipe.org) token:

```env
AI_PIPE_KEY=your_aipipe_token
# Optional: any OpenAI-compatible provider works
# LLM_MODEL=gpt-4o-mini
# LLM_BASE_URL=https://aipipe.org/openai/v1
```

**Web app:**

```bash
streamlit run app.py
```

**Batch pipeline:**

```bash
python pipeline.py              # OCR + LLM for every file in raw_documents/
python pipeline.py --reuse-ocr  # re-run only the LLM stages using OCR text saved in outputs/
```

Results are written to `outputs/`. OCR runs on CPU and takes roughly 30–60 seconds per document. `--reuse-ocr` skips it, which is handy when iterating on prompts.

## Deploy to Streamlit Cloud

1. On [share.streamlit.io](https://share.streamlit.io), click **Create app**: repository `insurance-doc-pipeline`, branch `main`, main file `app.py`.
2. In **Advanced settings**, choose Python **3.12** and add the secret `AI_PIPE_KEY = "your_aipipe_token"`.
3. Click **Deploy**. The first boot takes a few minutes while PyTorch installs.

The **Sample Results** tab needs no API calls, so reviewers can explore the outputs even if the API budget runs out.

---

## Project Structure

```text
insurance-doc-pipeline/
├── app.py                  # Streamlit web app (live processing + sample results browser)
├── pipeline.py             # OCR, classification, extraction, validation, review flagging
├── prompts.py              # Classification/extraction prompts and required fields per type
├── schemas.py              # Pydantic schema of the per-document JSON output
├── raw_documents/          # 12 sample documents (images and PDFs)
├── outputs/                # One JSON per document + human_review_flagging_report.json
├── requirements.txt
├── .env.example
└── README.md
```

---

# Methodology in Detail

## 1. Document Classification

Supported types: Aadhaar Card, PAN Card, Driving Licence, Passport, NACH / ECS Mandate, FATCA Annexure Form, Benefit Illustration Declaration, Moral Hazard Questionnaire, Multiple Policies Consent Form, Suitability Profiler Declaration, plus **Unknown**.

Each supported type gets a one-line description in the prompt, and the OCR text is passed inside clear delimiters. The pipeline enforces the model's decisions in code:

* `matches_supported_type: false` always results in `Unknown`.
* A `detected_label` that is literally a supported type name (e.g. "Moral Hazard Questionnaire") always maps to that type.
* Any label outside the supported list is routed to `Unknown`.

Unknown documents skip field extraction, since there is no field schema for them and the model would invent fields. Each one becomes a single `DOCUMENT_TYPE` review item:

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

In the sample set, the 10 supported types map one-to-one onto 10 documents. The two extra documents, an *Assignment Request Form* and a *Customer Declaration – Application/Proposal Form*, are flagged as Unknown. Classification was verified to be stable across three consecutive runs.

## 2. Extraction Output

Each document produces a JSON file (`outputs/ECS.json`, abbreviated):

```json
{
  "document_name": "ECS.jpeg",
  "document_type": "NACH / ECS Mandate",
  "detected_label": "NACH MANDATE INSTRUCTION",
  "is_handwritten": true,
  "ocr_text": "...",
  "extracted_data": {
    "Bank Name": { "value": "HDFC", "confidence": 0.95, "validation_passed": true },
    "IFSC Code": { "value": "SBICNCCISB", "confidence": 0.2, "validation_passed": false }
  }
}
```

## 3. Confidence Scoring

Confidence is scored per field, not per document. The LLM's initial confidence follows an explicit calibration scale:

| Initial confidence | Meaning |
|---|---|
| 0.90 – 1.00 | Clean, fully legible value in the expected format |
| 0.60 – 0.80 | Readable but with minor OCR noise, or uncertain spelling |
| 0.30 – 0.50 | Garbled value (e.g. "Kephew", "Lndean", "L500131olbob") or partial value ("West B", "26/2021") |
| 0.00 – 0.20 | A guess, or the value could not be located |

Deterministic adjustments then ground it in validation outcomes:

* Validation passed → +0.15
* Validation failed → −0.30
* Handwritten document → −0.10

The final score is clipped to the range 0.0–1.0.

## 4. Validation Rules

Field names are normalised (e.g. `Aadhaar Number` → `aadhaar_number`) before the rules run:

| Field | Rule | Example |
|---|---|---|
| Aadhaar Number | 12 digits (spaces ignored) | 1234 5678 9012 |
| PAN Number | `AAAAA9999A` | ABCDE1234F |
| Passport Number | `A1234567` | X1234567 |
| IFSC Code | `AAAA0XXXXXX` | SBIN0027112 |
| Date fields | DD/MM/YYYY, DD-MM-YYYY or DD.MM.YYYY | 15/06/2021 |
| Any field | Placeholder values (`"null"`, `"None"`, `"N/A"`, `"-"`) become `null` and fail | — |

## 5. Human Review Threshold

**0.80.** Fields below it are added to `outputs/human_review_flagging_report.json`, with document, type, field, value, confidence and reason (including whether validation failed).

* Handwritten forms naturally produce lower OCR quality.
* 0.80 balances extraction accuracy against reviewer workload.
* Higher thresholds generated excessive false review requests; lower ones let uncertain handwritten values through.

## 6. Handwritten Text Handling

1. The classifier flags forms whose filled-in values look handwritten: garbled or misspelt values, letters mixed into numbers, broken fragments next to printed labels.
2. Government ID cards are always treated as printed, so they never receive the handwriting penalty.
3. Handwritten documents take a −0.10 confidence penalty on every field.
4. Missing or low-confidence handwritten values are always routed to review, never silently accepted.

## 7. Failure Cases Observed

| Case | What happened | Outcome |
|---|---|---|
| ECS Mandate, IFSC code (actual `SBIN0027112`) | OCR merged handwritten and printed regions and returned `SBICNCCISB` | IFSC validation failed (0.2) → review |
| Place names and nationality (West Bihar, Indian) | Character substitutions: `WesdBeky`, `Wesl Bilnx Ran`, `Lndean` | Confidence 0.35 → review |
| Handwritten dates | Letter/digit confusion: `26/202L`, `26luks` | Date validation failed (0.0) → review |
| **Remaining limitation** | Misreadings that still look like valid words (e.g. "Asbok" for "Ashok") can score high | Cross-checking names across one applicant's documents would catch these |

## 8. Results on the Sample Set

12 documents processed (10 supported types + 2 Unknown), 44 fields extracted, 25 human review items.

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

Printed identity documents pass with high confidence, and every uncertain handwritten value is routed to a person.

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| OCR | EasyOCR (CPU) |
| PDF rendering | PyMuPDF |
| LLM | GPT-4o mini via [AI Pipe](https://aipipe.org) (OpenAI-compatible), LangChain `ChatOpenAI` |
| Validation | Regex and date rules |
| Output | Structured JSON + consolidated review report |
