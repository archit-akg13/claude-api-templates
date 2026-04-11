#!/usr/bin/env python3
"""
Claude API Streaming Chat Template
-----------------------------------
Interactive chat with Claude using streaming responses.
Supports conversation history, system prompts, and token usage tracking.

Requirements:
    pip install anthropic
    """

import sys
from typing import Optional

try:
      import anthropic
except ImportError:
      print("Error: anthropic package required. Install with: pip install anthropic")
      sys.exit(1)


class StreamingChat:
      """Interactive streaming chat session with Claude."""

    def __init__(
              self,
              model: str = "claude-sonnet-4-20250514",
              max_tokens: int = 1024,
              system_prompt: Optional[str] = None,
    ):
              self.client = anthropic.Anthropic()
              self.model = model
              self.max_tokens = max_tokens
              self.system_prompt = system_prompt or "You are a helpful assistant."
              self.messages: list[dict] = []
              self.total_input_tokens = 0
              self.total_output_tokens = 0

    def send_message(self, user_input: str) -> str:
              """Send a message and stream the response."""
              self.messages.append({"role": "user", "content": user_input})
              full_response = ""

        with self.client.messages.stream(
                      model=self.model,
                      max_tokens=self.max_tokens,
                      system=self.system_prompt,
                      messages=self.messages,
        ) as stream:
                      for text in stream.text_stream:
                                        print(text, end="", flush=True)
                                        full_response += text

                  # Track token usage
                  usage = stream.get_final_message().usage
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens

        self.messages.append({"role": "assistant", "content": full_response})
        print()
        return full_response

    def get_usage_summary(self) -> str:
              """Return token usage summary."""
              return (
                  f"Tokens used - Input: {self.total_input_tokens}, "
                  f"Output: {self.total_output_tokens}, "
                  f"Total: {self.total_input_tokens + self.total_output_tokens}"
              )

    def reset(self) -> None:
              """Clear conversation history and token counts."""
              self.messages.clear()
              self.total_input_tokens = 0
              self.total_output_tokens = 0


def main():
      """Run an interactive streaming chat session."""
      print("Claude Streaming Chat (type 'quit' to exit, 'usage' for token stats, 'reset' to clear history)")
      print("-" * 60)

    chat = StreamingChat(
              system_prompt="You are a helpful AI assistant. Be concise and clear.",
    )

    while True:
              try:
                            user_input = input("\nYou: ").strip()
except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
                      continue
                  if user_input.lower() == "quit":
                                print(f"\n{chat.get_usage_summary()}")
                                print("Goodbye!")
                                break
                            if user_input.lower() == "usage":
                                          print(chat.get_usage_summary())
                                          continue
                                      if user_input.lower() == "reset":
                                                    chat.reset()
                                                    print("Conversation history cleared.")
                                                    continue

        print("\nClaude: ", end="")
        chat.send_message(user_input)


if __name__ == "__main__":
      main()
