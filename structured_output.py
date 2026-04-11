#!/usr/bin/env python3
"""
Structured Output with Claude API — Extract typed, validated data from text.

Demonstrates how to use Claude to parse unstructured text into Pydantic models
with retry logic, token tracking, and batch processing support.

Usage:
    pip install anthropic pydantic
    export ANTHROPIC_API_KEY=your-key
    python structured_output.py

Author: Archit Mittal (@automate_archit)
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, TypeVar

try:
    from anthropic import Anthropic
except ImportError:
    raise ImportError("Run: pip install anthropic")

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    raise ImportError("Run: pip install pydantic")

T = TypeVar("T", bound=BaseModel)

# ── Configuration ──────────────────────────────────────────────
DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_RETRIES = 3
RETRY_DELAY = 1.0


# ── Example Pydantic Models ───────────────────────────────────
class ContactInfo(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None


class InvoiceItem(BaseModel):
    description: str
    quantity: int
    unit_price: float
    total: float


class Invoice(BaseModel):
    vendor: str
    invoice_number: str
    date: str
    items: List[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    currency: str = "USD"


class SentimentResult(BaseModel):
    sentiment: str  # positive, negative, neutral
    confidence: float
    key_phrases: List[str]
    summary: str


# ── Core Extraction Engine ────────────────────────────────────
@dataclass
class ExtractionResult:
    data: Any
    model_name: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    retries: int


def extract(
    text: str,
    schema: Type[T],
    model: str = DEFAULT_MODEL,
    system_prompt: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
) -> ExtractionResult:
    """
    Extract structured data from text using Claude.

    Args:
        text: The unstructured input text to parse.
        schema: A Pydantic model class defining the output shape.
        model: Claude model to use.
        system_prompt: Optional custom system prompt.
        max_retries: Number of retries on validation failure.

    Returns:
        ExtractionResult with parsed data and metadata.
    """
    client = Anthropic()
    schema_json = json.dumps(schema.model_json_schema(), indent=2)

    if not system_prompt:
        system_prompt = (
            "You are a precise data extraction assistant. "
            "Extract information from the provided text and return it as valid JSON "
            "matching the given schema. Only output the JSON object, no other text."
        )

    user_msg = (
        f"Extract data from the following text into this JSON schema:\n\n"
        f"Schema:\n```json\n{schema_json}\n```\n\n"
        f"Text:\n```\n{text}\n```\n\n"
        f"Return ONLY valid JSON matching the schema."
    )

    last_error = None
    for attempt in range(max_retries):
        start = time.monotonic()
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        latency = (time.monotonic() - start) * 1000

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            parsed = schema.model_validate_json(raw)
            return ExtractionResult(
                data=parsed,
                model_name=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=round(latency, 1),
                retries=attempt,
            )
        except (ValidationError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries - 1:
                user_msg += (
                    f"\n\nYour previous response had a validation error: {e}. "
                    f"Please fix and return valid JSON."
                )
                time.sleep(RETRY_DELAY)

    raise ValueError(f"Failed after {max_retries} attempts. Last error: {last_error}")


def extract_batch(
    texts: List[str],
    schema: Type[T],
    model: str = DEFAULT_MODEL,
) -> List[ExtractionResult]:
    """Extract structured data from multiple texts."""
    results = []
    for i, text in enumerate(texts):
        try:
            result = extract(text, schema, model)
            results.append(result)
            print(f"  [{i+1}/{len(texts)}] OK ({result.latency_ms}ms)")
        except ValueError as e:
            print(f"  [{i+1}/{len(texts)}] FAILED: {e}")
            results.append(None)
    return results


# ── Demo ──────────────────────────────────────────────────────
def demo_contact_extraction():
    print("\n--- Contact Extraction Demo ---")
    text = (
        "Hi, I'm Sarah Chen from Acme Corp. I'm the VP of Engineering. "
        "You can reach me at sarah.chen@acme.io or call 415-555-0142."
    )
    result = extract(text, ContactInfo)
    print(f"  Name:    {result.data.name}")
    print(f"  Email:   {result.data.email}")
    print(f"  Phone:   {result.data.phone}")
    print(f"  Company: {result.data.company}")
    print(f"  Role:    {result.data.role}")
    print(f"  Tokens:  {result.input_tokens} in / {result.output_tokens} out")
    print(f"  Latency: {result.latency_ms}ms (retries: {result.retries})")


def demo_sentiment():
    print("\n--- Sentiment Analysis Demo ---")
    text = (
        "The new automation platform is incredible. Setup took 10 minutes "
        "and it already saved us 20 hours this week. The API docs could be "
        "better, but overall we are very happy with the purchase."
    )
    result = extract(text, SentimentResult)
    print(f"  Sentiment:  {result.data.sentiment} ({result.data.confidence:.0%})")
    print(f"  Phrases:    {', '.join(result.data.key_phrases)}")
    print(f"  Summary:    {result.data.summary}")


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run demos.")
        print("Example models available: ContactInfo, Invoice, SentimentResult")
        print("Usage: result = extract('your text here', ContactInfo)")
    else:
        demo_contact_extraction()
        demo_sentiment()
