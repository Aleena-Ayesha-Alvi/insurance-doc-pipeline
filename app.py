import os
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline import (
    RAW_DIR,
    OUTPUT_DIR,
    REVIEW_REPORT_NAME,
    SUPPORTED_EXTENSIONS,
    CONFIDENCE_THRESHOLD,
    get_reader,
    process_document
)

st.set_page_config(page_title="Insurance Document Pipeline", page_icon="📄", layout="wide")
st.title("📄 Insurance Document Processing Pipeline")
st.caption(
    "OCR → Classification → Field Extraction → Validation → Confidence Scoring → Human Review Flagging"
)


# ---------------------------------------------------
# RENDERING
# ---------------------------------------------------

def render_result(output, review_items):

    col1, col2, col3 = st.columns(3)
    col1.metric("Document Type", output["document_type"])
    col2.metric("Detected Title", output.get("detected_label") or "-")
    col3.metric("Handwritten", "Yes" if output["is_handwritten"] else "No")

    if output["document_type"] == "Unknown":
        st.warning("Unrecognised document type. Field extraction skipped and routed to manual classification.")

    extracted = output.get("extracted_data", {})

    if extracted:
        rows = [
            {
                "Field": name,
                "Value": data.get("value"),
                "Confidence": data.get("confidence"),
                "Validation": "✅" if data.get("validation_passed") else "❌",
                "Needs Review": "⚠️" if data.get("confidence", 0) < CONFIDENCE_THRESHOLD else ""
            }
            for name, data in extracted.items()
        ]
        st.subheader("Extracted Fields")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.subheader(f"Human Review Items ({len(review_items)})")
    if review_items:
        st.dataframe(pd.DataFrame(review_items), hide_index=True, width="stretch")
    else:
        st.success(f"All fields passed the {CONFIDENCE_THRESHOLD:.2f} confidence threshold.")

    with st.expander("OCR Text"):
        st.text(output.get("ocr_text", ""))

    st.download_button(
        "Download JSON",
        data=json.dumps(output, indent=2),
        file_name=f"{Path(output['document_name']).stem}.json",
        mime="application/json"
    )


def show_preview(path):

    if Path(path).suffix.lower() != ".pdf":
        st.image(str(path), width="stretch")
    else:
        st.info("PDF document")


# ---------------------------------------------------
# TABS
# ---------------------------------------------------

process_tab, samples_tab = st.tabs(["🔍 Process a Document", "📂 Sample Results"])

with process_tab:

    has_key = bool(os.getenv("AI_PIPE_KEY"))

    if not has_key:
        st.error("AI_PIPE_KEY is not set. Add it to a `.env` file locally, or to the app's Secrets on Streamlit Cloud.")

    source = st.radio("Document source", ["Upload a file", "Use a sample document"], horizontal=True)

    doc_path, doc_name = None, None

    if source == "Upload a file":
        uploaded = st.file_uploader(
            "Upload an image or PDF",
            type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS]
        )
        if uploaded is not None:
            # One temp file per upload, reused across reruns
            suffix = Path(uploaded.name).suffix.lower()
            doc_path = Path(tempfile.gettempdir()) / f"docpipeline_{uploaded.file_id}{suffix}"
            if not doc_path.exists():
                doc_path.write_bytes(uploaded.getvalue())
            doc_name = uploaded.name
    else:
        samples = sorted(
            f for f in os.listdir(RAW_DIR)
            if f.lower().endswith(SUPPORTED_EXTENSIONS)
        )
        doc_name = st.selectbox("Sample document", samples)
        doc_path = RAW_DIR / doc_name

    if doc_path is not None:

        preview_col, result_col = st.columns([1, 2])

        with preview_col:
            show_preview(doc_path)

        with result_col:
            if st.button("Run Pipeline", type="primary", disabled=not has_key):
                try:
                    with st.spinner("Loading OCR model (the first run downloads it)..."):
                        get_reader()
                    with st.spinner("Running OCR, classification and extraction..."):
                        # Keep the result across reruns (e.g. clicking Download)
                        st.session_state["last_result"] = (
                            doc_name,
                            process_document(doc_path, filename=doc_name)
                        )
                except Exception as e:
                    st.session_state.pop("last_result", None)
                    st.error(f"Pipeline failed: {e}")

            last = st.session_state.get("last_result")
            if last and last[0] == doc_name:
                render_result(*last[1])

with samples_tab:

    st.write("Precomputed results for the 12 sample documents in `raw_documents/` (no API calls).")

    result_files = sorted(
        f for f in OUTPUT_DIR.glob("*.json")
        if f.name != REVIEW_REPORT_NAME
    )
    report_path = OUTPUT_DIR / REVIEW_REPORT_NAME
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else []

    if not result_files:
        st.info("No precomputed results found. Run `python pipeline.py` to generate them.")
    else:
        summary = []
        for f in result_files:
            data = json.loads(f.read_text(encoding="utf-8"))
            summary.append({
                "Document": data["document_name"],
                "Type": data["document_type"],
                "Handwritten": data["is_handwritten"],
                "Fields": len(data.get("extracted_data", {})),
                "Review Items": sum(1 for r in report if r["document"] == data["document_name"])
            })
        st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")

        selected = st.selectbox("Inspect a document", [f.stem for f in result_files])
        output = json.loads((OUTPUT_DIR / f"{selected}.json").read_text(encoding="utf-8"))

        preview_col, result_col = st.columns([1, 2])
        with preview_col:
            show_preview(RAW_DIR / output["document_name"])
        with result_col:
            render_result(
                output,
                [r for r in report if r["document"] == output["document_name"]]
            )

        with st.expander(f"Full Human Review Report ({len(report)} items)"):
            st.dataframe(pd.DataFrame(report), hide_index=True, width="stretch")
