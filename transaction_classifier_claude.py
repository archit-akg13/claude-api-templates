"""
transaction_classifier_claude.py
=================================
Use Claude to classify "Other"-bucket transactions that the regex/keyword
categorizer in automation-scripts/upi_categorizer.py couldn't auto-tag.

Pipeline:
    1. Run upi_categorizer.py on a statement to produce upi_summary.csv
       and a per-row tagged file with category="Other" rows.
    2. Pass those rows to this script — Claude returns JSON predictions
       which you merge back into the summary.

Designed for the long tail: regional kiranas, weird merchant slugs,
salary credits with payroll-vendor names. Keyword-based categorizer
handles the head of the distribution; this handles the tail.

Companion writeup: https://dev.to/automate-archit/build-a-upi-transaction-categorizer-in-95-lines-of-python-2g8f
"""
import json
import os
import sys
from pathlib import Path
from typing import Iterable

import anthropic

CATEGORIES = [
    "Food", "Groceries", "Transport", "Bills", "Shopping",
    "Investments", "Health", "Entertainment", "Salary",
    "Rent", "Insurance", "Education", "Other",
]

SYSTEM_PROMPT = f"""You classify Indian bank/UPI transaction narrations into spending categories.

Allowed categories: {', '.join(CATEGORIES)}.

Rules:
- Reply ONLY with a JSON array of objects: [{{"narration": "...", "category": "..."}}].
- "category" must be one of the allowed values, case-sensitive.
- Use "Other" only when no category clearly fits.
- Do not invent narrations; echo each input narration verbatim.
"""


def classify(narrations: Iterable[str], model: str = "claude-haiku-4-5-20251001") -> list[dict]:
    """Return [{"narration": ..., "category": ...}, ...] for each input."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    payload = json.dumps(list(narrations), ensure_ascii=False, indent=2)
    msg = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Classify these {len(list(narrations))} narrations:\n{payload}",
        }],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    return json.loads(text)


def main(path: Path) -> None:
    narrations = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if not narrations:
        print("No narrations found in", path, file=sys.stderr)
        sys.exit(2)
    # Process in chunks of 50 to keep prompts tight.
    out: list[dict] = []
    for i in range(0, len(narrations), 50):
        out.extend(classify(narrations[i:i + 50]))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transaction_classifier_claude.py <narrations.txt>", file=sys.stderr)
        sys.exit(1)
    main(Path(sys.argv[1]))
