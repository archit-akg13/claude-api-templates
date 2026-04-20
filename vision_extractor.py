"""vision_extractor.py — Extract structured data from images using Claude vision.

Pattern this template demonstrates:
    Send a local image (PNG / JPG / GIF / WebP) or a remote URL to Claude as a
    multimodal message, prompt the model with a JSON schema describing the
    fields to extract, and validate the response with Pydantic before returning.

Use cases:
    - Pull line items, totals, and tax from a receipt photo
    - Read meter / odometer / scale readings into structured numbers
    - Extract speaker, title, and date from a slide screenshot
    - Parse a whiteboard photo into a list of action items

Quick start:
    export ANTHROPIC_API_KEY=sk-ant-...
    pip install anthropic pydantic

    python vision_extractor.py receipt.jpg --schema receipt
    python vision_extractor.py https://example.com/invoice.png --schema invoice
    python vision_extractor.py photo.jpg --fields vendor,total,date

Exit codes:
    0 — extraction succeeded and validated against the schema
    1 — API error after retries, or schema validation failed
    2 — invalid usage (missing file, unsupported MIME type, etc.)
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel, Field, ValidationError

DEFAULT_MODEL = "claude-sonnet-4-6"
SUPPORTED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}

log = logging.getLogger("vision_extractor")


# ---------------------------------------------------------------------------
# Built-in schemas. Add your own by subclassing BaseModel and registering it
# in SCHEMAS below — the --schema flag will pick them up automatically.
# ---------------------------------------------------------------------------

class ReceiptLineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    total: float


class Receipt(BaseModel):
    vendor: str
    date: str | None = Field(None, description="ISO 8601 date if present, else null")
    currency: str | None = Field(None, description="ISO 4217 code (USD, EUR, INR, ...)")
    line_items: list[ReceiptLineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float


class Invoice(BaseModel):
    invoice_number: str | None = None
    issue_date: str | None = None
    due_date: str | None = None
    vendor: str
    customer: str | None = None
    line_items: list[ReceiptLineItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float


SCHEMAS: dict[str, type[BaseModel]] = {
    "receipt": Receipt,
    "invoice": Invoice,
}


# ---------------------------------------------------------------------------
# Image loading — local files become base64 blocks, http(s) URLs pass through.
# ---------------------------------------------------------------------------

def build_image_block(source: str) -> dict[str, Any]:
    """Build a Claude image content block for either a local path or URL."""
    if source.startswith(("http://", "https://")):
        return {"type": "image", "source": {"type": "url", "url": source}}

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"image not found: {source}")

    mime, _ = mimetypes.guess_type(path.name)
    if mime not in SUPPORTED_MIME:
        raise ValueError(f"unsupported image type {mime!r}; expected one of {sorted(SUPPORTED_MIME)}")

    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime, "data": data},
    }


# ---------------------------------------------------------------------------
# Prompt construction — describe the schema in plain English so the model
# returns JSON we can validate.
# ---------------------------------------------------------------------------

def build_extraction_prompt(schema_cls: type[BaseModel] | None, ad_hoc_fields: list[str] | None) -> str:
    if schema_cls is not None:
        schema_json = json.dumps(schema_cls.model_json_schema(), indent=2)
        return (
            "You are an information extraction assistant. Read the attached image "
            "carefully and return a JSON object that conforms to the schema below. "
            "If a field cannot be determined from the image, return null (or an "
            "empty list for arrays). Return ONLY the JSON object — no prose, no "
            "code fences.\n\n"
            f"Schema:\n{schema_json}"
        )

    fields = ad_hoc_fields or ["summary"]
    fields_block = "\n".join(f'  - "{f}": ...' for f in fields)
    return (
        "Extract the following fields from the attached image and return them as "
        "a single JSON object. Return ONLY the JSON object — no prose, no code "
        f"fences.\n\nFields:\n{fields_block}"
    )


# ---------------------------------------------------------------------------
# Core extraction call.
# ---------------------------------------------------------------------------

def extract(
    image_source: str,
    schema_cls: type[BaseModel] | None = None,
    ad_hoc_fields: list[str] | None = None,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any]:
    """Send the image, parse the JSON response, validate against the schema."""
    client = client or anthropic.Anthropic()
    image_block = build_image_block(image_source)
    prompt = build_extraction_prompt(schema_cls, ad_hoc_fields)

    log.info("calling %s for extraction (schema=%s)", model, schema_cls.__name__ if schema_cls else "ad-hoc")
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [image_block, {"type": "text", "text": prompt}],
        }],
    )

    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    if not text:
        raise RuntimeError("model returned no text content")

    # Tolerate a stray code fence even though we asked for raw JSON.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"model did not return valid JSON: {exc}\n---\n{text[:500]}") from exc

    if schema_cls is not None:
        try:
            validated = schema_cls.model_validate(payload)
        except ValidationError as exc:
            raise RuntimeError(f"schema validation failed:\n{exc}") from exc
        return validated.model_dump(mode="json")

    return payload


# ---------------------------------------------------------------------------
# CLI plumbing.
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vision_extractor",
        description="Extract structured data from an image using Claude vision.",
    )
    parser.add_argument("image", help="path to a local image file or an http(s) URL")
    schema_group = parser.add_mutually_exclusive_group()
    schema_group.add_argument(
        "--schema",
        choices=sorted(SCHEMAS),
        help="use a built-in Pydantic schema for validation",
    )
    schema_group.add_argument(
        "--fields",
        help="comma-separated list of ad-hoc fields to extract (no validation)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"model to call (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-tokens", type=int, default=2048, help="response token budget")
    parser.add_argument("--log-level", default="WARNING", help="logging level (DEBUG, INFO, WARNING, ...)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set in the environment", file=sys.stderr)
        return 2

    schema_cls = SCHEMAS[args.schema] if args.schema else None
    fields = [f.strip() for f in args.fields.split(",")] if args.fields else None

    try:
        result = extract(
            args.image,
            schema_cls=schema_cls,
            ad_hoc_fields=fields,
            model=args.model,
            max_tokens=args.max_tokens,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (anthropic.APIError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
