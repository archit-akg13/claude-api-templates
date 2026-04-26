"""Extract structured invoice data from a PDF using the Claude API.

Demonstrates Claude's vision capability for parsing scanned/digital invoices
into a clean JSON object — ideal for AP automation, GST reconciliation,
or expense reports.

Setup:
    pip install anthropic pypdf2
    export ANTHROPIC_API_KEY=sk-ant-...

Usage:
    python claude_invoice_extractor.py path/to/invoice.pdf
"""
import base64
import json
import sys
from pathlib import Path

import anthropic

EXTRACTION_SCHEMA = {
    "vendor_name": "string",
    "vendor_gstin": "string or null",
    "invoice_number": "string",
    "invoice_date": "YYYY-MM-DD",
    "currency": "string (e.g. INR)",
    "subtotal": "number",
    "tax_amount": "number",
    "total": "number",
    "line_items": [
        {"description": "string", "quantity": "number",
         "unit_price": "number", "line_total": "number"}
    ],
}

PROMPT = f"""You are an invoice extraction assistant. Read the attached
invoice and return ONLY a JSON object matching this schema (no prose,
no code fences):

{json.dumps(EXTRACTION_SCHEMA, indent=2)}

If a field is missing on the invoice, use null. Numbers must be plain
numerics (no currency symbols, no commas)."""


def extract_invoice(pdf_path: str) -> dict:
    pdf_bytes = Path(pdf_path).read_bytes()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf",
                            "data": pdf_b64}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    text = response.content[0].text.strip()
    return json.loads(text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python claude_invoice_extractor.py <invoice.pdf>")
    data = extract_invoice(sys.argv[1])
    print(json.dumps(data, indent=2, ensure_ascii=False))
