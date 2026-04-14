#!/usr/bin/env python3
"""
Batch Processor for Claude API — process multiple prompts with concurrency control.

Features:
  - Async batch processing with configurable concurrency
  - Automatic retry with exponential backoff
  - Progress tracking and result aggregation
  - CSV/JSON input and output support
  - Rate limit handling with adaptive throttling

Usage:
  python batch_processor.py prompts.csv --output results.json --concurrency 5
  python batch_processor.py prompts.json --model claude-sonnet-4-20250514 --max-tokens 1024
"""

import asyncio
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from anthropic import AsyncAnthropic, RateLimitError, APIError
except ImportError:
    print("Install the Anthropic SDK: pip install anthropic")
    sys.exit(1)


@dataclass
class BatchItem:
    """Represents a single item in the batch."""
    id: str
    prompt: str
    system: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    result: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    tokens_used: int = 0


@dataclass
class BatchResult:
    """Aggregated results from a batch run."""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    items: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.succeeded, 1)


class BatchProcessor:
    """Process multiple Claude API requests with concurrency and retry logic."""

    def __init__(
        self,
        concurrency: int = 5,
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: float = 60.0,
    ):
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout
        self.client = AsyncAnthropic()
        self._semaphore = asyncio.Semaphore(concurrency)
        self._progress_count = 0
        self._total_count = 0

    async def process_item(self, item: BatchItem) -> BatchItem:
        """Process a single batch item with retry logic."""
        async with self._semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    start = time.monotonic()
                    messages = [{"role": "user", "content": item.prompt}]
                    kwargs = {
                        "model": item.model,
                        "max_tokens": item.max_tokens,
                        "messages": messages,
                    }
                    if item.system:
                        kwargs["system"] = item.system

                    response = await asyncio.wait_for(
                        self.client.messages.create(**kwargs),
                        timeout=self.timeout,
                    )
                    elapsed = (time.monotonic() - start) * 1000

                    item.result = response.content[0].text
                    item.latency_ms = round(elapsed, 2)
                    item.tokens_used = (
                        response.usage.input_tokens + response.usage.output_tokens
                    )
                    break

                except RateLimitError:
                    delay = self.base_delay * (2 ** attempt)
                    print(f"  Rate limited on {item.id}, retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)

                except (APIError, asyncio.TimeoutError) as e:
                    if attempt == self.max_retries:
                        item.error = f"{type(e).__name__}: {e}"
                    else:
                        delay = self.base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)

                except Exception as e:
                    item.error = f"{type(e).__name__}: {e}"
                    break

            self._progress_count += 1
            status = "OK" if item.result else "FAIL"
            print(f"  [{self._progress_count}/{self._total_count}] {item.id}: {status}")
            return item

    async def run(self, items: List[BatchItem]) -> BatchResult:
        """Process all items concurrently and return aggregated results."""
        self._total_count = len(items)
        self._progress_count = 0

        print(f"Processing {len(items)} items (concurrency={self.concurrency})...")
        start = time.monotonic()

        tasks = [self.process_item(item) for item in items]
        completed = await asyncio.gather(*tasks)

        elapsed = time.monotonic() - start
        result = BatchResult(total=len(completed))

        for item in completed:
            if item.result:
                result.succeeded += 1
                result.total_tokens += item.tokens_used
                result.total_latency_ms += item.latency_ms
            else:
                result.failed += 1
            result.items.append(asdict(item))

        print(f"\nDone in {elapsed:.1f}s — {result.succeeded} ok, {result.failed} failed")
        print(f"Total tokens: {result.total_tokens:,} | Avg latency: {result.avg_latency_ms:.0f}ms")
        return result


def load_items(filepath: str, model: str = "", max_tokens: int = 0) -> List[BatchItem]:
    """Load batch items from a CSV or JSON file."""
    path = Path(filepath)
    items = []

    if path.suffix == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                items.append(BatchItem(
                    id=row.get("id", f"item_{i}"),
                    prompt=row["prompt"],
                    system=row.get("system", ""),
                    model=model or row.get("model", "claude-sonnet-4-20250514"),
                    max_tokens=max_tokens or int(row.get("max_tokens", 1024)),
                ))
    elif path.suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for i, entry in enumerate(data):
                if isinstance(entry, str):
                    items.append(BatchItem(id=f"item_{i}", prompt=entry))
                else:
                    items.append(BatchItem(
                        id=entry.get("id", f"item_{i}"),
                        prompt=entry["prompt"],
                        system=entry.get("system", ""),
                        model=model or entry.get("model", "claude-sonnet-4-20250514"),
                        max_tokens=max_tokens or entry.get("max_tokens", 1024),
                    ))
    else:
        raise ValueError(f"Unsupported file format: {path.suffix} (use .csv or .json)")

    return items


def save_results(result: BatchResult, filepath: str) -> None:
    """Save batch results to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2, ensure_ascii=False)
    print(f"Results saved to {filepath}")


async def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    args = sys.argv[1:]
    input_file = args[0]

    # Parse optional arguments
    model = ""
    max_tokens = 0
    output = "batch_results.json"
    concurrency = 5

    i = 1
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]; i += 2
        elif args[i] == "--max-tokens" and i + 1 < len(args):
            max_tokens = int(args[i + 1]); i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output = args[i + 1]; i += 2
        elif args[i] == "--concurrency" and i + 1 < len(args):
            concurrency = int(args[i + 1]); i += 2
        else:
            i += 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: Set ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    items = load_items(input_file, model=model, max_tokens=max_tokens)
    processor = BatchProcessor(concurrency=concurrency)
    result = await processor.run(items)
    save_results(result, output)


if __name__ == "__main__":
    asyncio.run(main())
