"""
pdf_qa.py
---------
Ask questions over one or more PDFs using Claude's native document support.

This template shows the recommended pattern for Claude PDF Q&A:
  1. Read each PDF as bytes and base64-encode it.
  2. Wrap each file in a `document` content block on the user turn.
  3. Send a natural-language question alongside the documents.
  4. Iterate — Claude keeps the PDFs in context across follow-ups.

Environment:
  ANTHROPIC_API_KEY  must be set.

Usage:
    python pdf_qa.py --pdf report.pdf --question "What was revenue in Q3?"
    python pdf_qa.py --pdf a.pdf --pdf b.pdf   # interactive multi-turn chat
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path
from typing import List

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    sys.stderr.write("Install the Anthropic SDK: pip install anthropic\n")
    raise

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_PDF_BYTES = 32 * 1024 * 1024  # 32 MB per file (Claude limit at time of writing)


def load_pdf_block(path: Path) -> dict:
    """Read `path` and return a Claude `document` content block."""
    data = path.read_bytes()
    if len(data) > MAX_PDF_BYTES:
        raise ValueError(f"{path.name} exceeds {MAX_PDF_BYTES} bytes")
    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
        "title": path.name,
        "citations": {"enabled": True},
    }


def build_initial_message(pdf_paths: List[Path], question: str) -> dict:
    """Return the first user message with all PDFs attached and a question."""
    blocks: List[dict] = [load_pdf_block(p) for p in pdf_paths]
    blocks.append({"type": "text", "text": question})
    return {"role": "user", "content": blocks}


def _extract_text(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def ask_once(
    client: Anthropic,
    pdf_paths: List[Path],
    question: str,
    *,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
) -> str:
    """Send a single Q&A request and return Claude's answer as plain text."""
    messages = [build_initial_message(pdf_paths, question)]
    kwargs = {"model": model, "max_tokens": 2048, "messages": messages}
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return _extract_text(response)


def chat(
    client: Anthropic,
    pdf_paths: List[Path],
    *,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
) -> None:
    """Interactive multi-turn REPL — PDFs are attached once on turn 1."""
    history: List[dict] = []
    print(f"Loaded {len(pdf_paths)} PDF(s). Ask a question (Ctrl-D to exit).")
    first_turn = True
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not question:
            continue

        if first_turn:
            history.append(build_initial_message(pdf_paths, question))
            first_turn = False
        else:
            history.append({"role": "user", "content": [{"type": "text", "text": question}]})

        kwargs = {"model": model, "max_tokens": 2048, "messages": history}
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        answer = _extract_text(response)
        history.append({"role": "assistant", "content": response.content})
        print(answer + "\n")


def _parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ask questions over PDFs with Claude.")
    p.add_argument("--pdf", type=Path, action="append", required=True, help="Path to a PDF (repeatable)")
    p.add_argument("--question", help="One-shot question. Omit for interactive chat.")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Model id (default: {DEFAULT_MODEL})")
    p.add_argument("--system", help="Optional system prompt for steering behavior")
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv)
    for p in args.pdf:
        if not p.exists():
            sys.stderr.write(f"PDF not found: {p}\n")
            return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write("ANTHROPIC_API_KEY environment variable is required.\n")
        return 2

    client = Anthropic()
    if args.question:
        print(ask_once(client, args.pdf, args.question, model=args.model, system=args.system))
    else:
        chat(client, args.pdf, model=args.model, system=args.system)
    return 0


if __name__ == "__main__":
    sys.exit(main())

