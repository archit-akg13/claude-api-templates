# claude-api-templates

Ready-to-use Claude API integration scripts — structured outputs, streaming, tool use, batch processing, and embeddings.

Drop these into any Python project that calls the Claude API. Each script is self-contained, type-hinted, and demonstrates a single integration pattern end-to-end.

## Templates

| Template | What it shows |
|----------|---------------|
| `structured_output.py` | Force JSON-shaped responses with a Pydantic schema and validate them |
| `streaming_chat.py` | Token-by-token streaming with backpressure and clean SIGINT handling |
| `tool_use_agent.py` | A minimal tool-calling loop with retries and tool-result feedback |
| `batch_processor.py` | Submit, poll, and reduce a Message Batch with idempotent retries |
| `conversation_memory.py` | Multi-turn conversation with rolling summary + truncation strategy |
| `prompt_cache_helper.py` | Wrap any prompt with cache breakpoints and report cache hit rates |
| `token_counter.py` | Count tokens before sending; estimate cost using current model pricing |

## Quick Start

```bash
git clone https://github.com/archit-akg13/claude-api-templates.git
cd claude-api-templates

python -m venv .venv && source .venv/bin/activate
pip install anthropic pydantic

export ANTHROPIC_API_KEY=sk-ant-...

# Run any template directly
python structured_output.py
python streaming_chat.py "Explain rate limiting in one paragraph."
python token_counter.py --model claude-sonnet-4-6 --file ./long_doc.txt
```

## Conventions

Every template follows a small set of rules so they stay drop-in friendly:

- **One file, one pattern.** No shared utility module — each script is readable top-to-bottom.
- **`ANTHROPIC_API_KEY` from the environment.** Never hardcoded, never read from a file.
- **Defaults pinned to `claude-sonnet-4-6`.** Override with `--model` on any template.
- **Structured logging to stderr.** Output goes to stdout so scripts compose with pipes.
- **Exit codes:** `0` success, `1` API error after retries, `2` invalid usage.

## Picking a Template

Not sure where to start? Use this rough mapping from the problem you have to the template that solves it:

- **"I need the model to return JSON I can parse."** → `structured_output.py`
- **"My UI needs to render tokens as they arrive."** → `streaming_chat.py`
- **"The model should call my functions to look things up."** → `tool_use_agent.py`
- **"I have 10K prompts to run cheaply overnight."** → `batch_processor.py`
- **"My chat app needs memory across turns without blowing the context window."** → `conversation_memory.py`
- **"I'm sending the same long context many times."** → `prompt_cache_helper.py`
- **"I need to estimate cost before I send the request."** → `token_counter.py`

## License

MIT — use these in your own projects, commercial or otherwise.
# claude-api-templates
Ready-to-use Claude API integration scripts — structured outputs, streaming, tool use, batch processing, and embeddings.
## Choosing the right template

Quick guide for picking the right starting point:

- **One-off, structured data extraction (form, invoice, JSON record)** → start with `structured_output.py`. Pydantic schema gives you validation for free and the prompt is short.
- - **Anything user-facing where waiting feels slow** → `streaming_chat.py`. The backpressure handling matters more than people expect once you put it under real load.
  - - **Need Claude to look things up or call your code mid-conversation** → `tool_use_agent.py`. Read the tool-result loop carefully — the SDK does not retry tool errors for you.
    - - **Bulk processing where latency doesn't matter** → `batch_processor.py`. Use this any time the dataset is over ~500 prompts. The cost savings vs. real-time calls are large enough that batching is worth the operational complexity.
      - - **Long-running conversations with state** → `conversation_memory.py`. Watch the token budget; the helper trims oldest turns automatically but you should log when it does.
       
        - ## Environment
       
        - These templates expect a single environment variable:
       
        - ```bash
          export ANTHROPIC_API_KEY=sk-ant-...
          ```

          Each script reads it with `os.environ["ANTHROPIC_API_KEY"]` and fails loudly if it is missing — no silent fallback to an empty string. If you prefer a `.env` file, install `python-dotenv` and add `load_dotenv()` at the top of the script; the rest works unchanged.

          ## Versioning

          Templates are pinned against the `anthropic` Python SDK version listed in each script's docstring. When the SDK has a breaking change, the affected templates get a follow-up commit with a one-line note in the docstring describing the migration. Older versions stay reachable via git history rather than living as duplicate files.
          
