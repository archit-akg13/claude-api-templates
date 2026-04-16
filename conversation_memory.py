#!/usr/bin/env python3
"""
Conversation Memory — manage multi-turn Claude conversations with persistence.

Provides a ConversationMemory class that handles message history,
token-aware truncation, and local JSON persistence for building
chatbots and multi-turn agents with the Claude API.

Usage:
    from conversation_memory import ConversationMemory

        memory = ConversationMemory(max_turns=50, system_prompt="You are helpful.")
            memory.add_user("What is Python?")
                response = memory.send(client)  # sends full history to Claude
                    memory.add_assistant(response)
                        memory.save("chat_session.json")
                        """

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
      import anthropic
except ImportError:
      anthropic = None


@dataclass
class Message:
      role: str
      content: str
      timestamp: float = field(default_factory=time.time)

    def to_api_dict(self) -> dict:
              return {"role": self.role, "content": self.content}


class ConversationMemory:
      """Manages conversation history with truncation and persistence."""

    def __init__(
              self,
              max_turns: int = 100,
              system_prompt: str = "",
              model: str = "claude-sonnet-4-20250514",
              max_tokens: int = 1024,
    ):
              self.messages: list[Message] = []
              self.max_turns = max_turns
              self.system_prompt = system_prompt
              self.model = model
              self.max_tokens = max_tokens
              self._metadata: dict = {}

    def add_user(self, content: str) -> None:
              """Add a user message to the conversation."""
              self.messages.append(Message(role="user", content=content))
              self._enforce_limit()

    def add_assistant(self, content: str) -> None:
              """Add an assistant message to the conversation."""
              self.messages.append(Message(role="assistant", content=content))
              self._enforce_limit()

    def _enforce_limit(self) -> None:
              """Trim oldest messages if we exceed max_turns (keep pairs)."""
              while len(self.messages) > self.max_turns * 2:
                            self.messages.pop(0)
                            if self.messages and self.messages[0].role == "assistant":
                                              self.messages.pop(0)

                    def get_api_messages(self) -> list[dict]:
                              """Return messages formatted for the Claude API."""
                              return [m.to_api_dict() for m in self.messages]

    def send(self, client: Optional[object] = None) -> str:
              """Send the conversation to Claude and return the response text.

                      If no client is provided, creates one from ANTHROPIC_API_KEY env var.
                              """
        if anthropic is None:
                      raise ImportError("pip install anthropic")

        if client is None:
                      client = anthropic.Anthropic()

        kwargs = {
                      "model": self.model,
                      "max_tokens": self.max_tokens,
                      "messages": self.get_api_messages(),
        }
        if self.system_prompt:
                      kwargs["system"] = self.system_prompt

        response = client.messages.create(**kwargs)
        text = response.content[0].text
        self.add_assistant(text)
        return text

    def clear(self) -> None:
              """Clear all messages."""
        self.messages.clear()

    @property
    def turn_count(self) -> int:
              """Number of user-assistant turn pairs."""
        return sum(1 for m in self.messages if m.role == "user")

    @property
    def last_message(self) -> Optional[str]:
              """Return the last message content, or None if empty."""
        return self.messages[-1].content if self.messages else None

    def summary(self) -> dict:
              """Return a summary of the conversation state."""
              return {
                  "turns": self.turn_count,
                  "total_messages": len(self.messages),
                  "model": self.model,
                  "system_prompt_set": bool(self.system_prompt),
                  "estimated_chars": sum(len(m.content) for m in self.messages),
              }

    def save(self, path: str | Path) -> None:
              """Persist conversation to a JSON file."""
              data = {
                  "system_prompt": self.system_prompt,
                  "model": self.model,
                  "max_turns": self.max_turns,
                  "max_tokens": self.max_tokens,
                  "metadata": self._metadata,
                  "messages": [
                      {
                          "role": m.role,
                          "content": m.content,
                          "timestamp": m.timestamp,
                      }
                      for m in self.messages
                  ],
              }
              Path(path).write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "ConversationMemory":
              """Load a conversation from a JSON file."""
              data = json.loads(Path(path).read_text())
              memory = cls(
                  max_turns=data.get("max_turns", 100),
                  system_prompt=data.get("system_prompt", ""),
                  model=data.get("model", "claude-sonnet-4-20250514"),
                  max_tokens=data.get("max_tokens", 1024),
              )
              memory._metadata = data.get("metadata", {})
              for msg in data.get("messages", []):
                            memory.messages.append(
                                              Message(
                                                                    role=msg["role"],
                                                                    content=msg["content"],
                                                                    timestamp=msg.get("timestamp", 0),
                                              )
                            )
                        return memory

    def fork(self, last_n_turns: Optional[int] = None) -> "ConversationMemory":
              """Create a copy of this conversation, optionally keeping only recent turns."""
        new = ConversationMemory(
                      max_turns=self.max_turns,
                      system_prompt=self.system_prompt,
                      model=self.model,
                      max_tokens=self.max_tokens,
        )
        msgs = self.messages
        if last_n_turns is not None:
                      keep = last_n_turns * 2
                      msgs = msgs[-keep:]
                  new.messages = [Message(m.role, m.content, m.timestamp) for m in msgs]
        return new


if __name__ == "__main__":
      mem = ConversationMemory(system_prompt="You are a helpful coding assistant.")
    mem.add_user("What is a decorator in Python?")
    mem.add_assistant(
              "A decorator is a function that wraps another function to extend "
              "its behavior without modifying its source code. You apply it with "
              "the @decorator syntax above a function definition."
    )
    mem.add_user("Can you show a simple example?")
    mem.add_assistant(
              "def my_decorator(func):\n"
              "    def wrapper(*args, **kwargs):\n"
              "        print('Before call')\n"
              "        result = func(*args, **kwargs)\n"
              "        print('After call')\n"
              "        return result\n"
              "    return wrapper\n\n"
              "@my_decorator\n"
              "def greet(name):\n"
              "    print(f'Hello, {name}!')"
    )

    print("Summary:", json.dumps(mem.summary(), indent=2))
    mem.save("/tmp/demo_chat.json")
    print("Saved to /tmp/demo_chat.json")

    loaded = ConversationMemory.load("/tmp/demo_chat.json")
    print(f"Loaded {loaded.turn_count} turns from disk.")
