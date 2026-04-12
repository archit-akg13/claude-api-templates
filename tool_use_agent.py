"""
Tool Use Agent — A reusable agentic loop using Claude's tool_use feature.

This module implements a lightweight agent that:
  - Sends messages to Claude with a set of tool definitions
    - Automatically executes tool calls returned by Claude
      - Feeds tool results back into the conversation
        - Loops until Claude produces a final text response (no more tool calls)

        Usage:
            from tool_use_agent import ToolUseAgent

                agent = ToolUseAgent(tools=[get_weather, search_docs])
                    response = agent.run("What's the weather in NYC and find docs about caching?")
                    """

import os
import json
import inspect
from typing import Any, Callable
from anthropic import Anthropic


def function_to_tool_schema(func: Callable) -> dict:
      """Convert a Python function into a Claude tool schema using its docstring and type hints."""
      sig = inspect.signature(func)
      doc = inspect.getdoc(func) or ""
      lines = doc.strip().split("\n")
      description = lines[0] if lines else func.__name__

    properties = {}
    required = []
    for name, param in sig.parameters.items():
              prop: dict[str, Any] = {"type": "string", "description": f"Parameter: {name}"}
              if param.annotation == int:
                            prop["type"] = "integer"
elif param.annotation == float:
            prop["type"] = "number"
elif param.annotation == bool:
            prop["type"] = "boolean"
        properties[name] = prop
        if param.default is inspect.Parameter.empty:
                      required.append(name)

    return {
              "name": func.__name__,
              "description": description,
              "input_schema": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
              },
    }


class ToolUseAgent:
      """A minimal agentic loop that lets Claude call Python functions as tools."""

    def __init__(
              self,
              tools: list[Callable],
              model: str = "claude-sonnet-4-20250514",
              max_iterations: int = 10,
              system_prompt: str = "You are a helpful assistant with access to tools.",
    ):
              self.client = Anthropic()
              self.model = model
              self.max_iterations = max_iterations
              self.system_prompt = system_prompt

        # Build registry: name -> (schema, callable)
              self._registry: dict[str, tuple[dict, Callable]] = {}
              for func in tools:
                            schema = function_to_tool_schema(func)
                            self._registry[schema["name"]] = (schema, func)

          @property
    def tool_schemas(self) -> list[dict]:
              return [schema for schema, _ in self._registry.values()]

    def _execute_tool(self, name: str, input_args: dict) -> str:
              """Look up and execute a registered tool, returning its result as a string."""
              if name not in self._registry:
                            return json.dumps({"error": f"Unknown tool: {name}"})
                        _, func = self._registry[name]
        try:
                      result = func(**input_args)
                      return json.dumps(result) if not isinstance(result, str) else result
except Exception as exc:
            return json.dumps({"error": str(exc)})

    def run(self, user_message: str) -> str:
              """Run the agentic loop: send user message, execute tools, return final answer."""
        messages = [{"role": "user", "content": user_message}]

        for _ in range(self.max_iterations):
                      response = self.client.messages.create(
                                        model=self.model,
                                        max_tokens=4096,
                                        system=self.system_prompt,
                                        tools=self.tool_schemas,
                                        messages=messages,
                      )

            # If stop_reason is "end_turn", extract text and return
                      if response.stop_reason == "end_turn":
                                        return "\n".join(
                                                              block.text for block in response.content if hasattr(block, "text")
                                        )

                      # Otherwise, process tool_use blocks
                      tool_results = []
                      for block in response.content:
                                        if block.type == "tool_use":
                                                              result = self._execute_tool(block.name, block.input)
                                                              tool_results.append(
                                                                  {
                                                                      "type": "tool_result",
                                                                      "tool_use_id": block.id,
                                                                      "content": result,
                                                                  }
                                                              )

                                    if not tool_results:
                                                      # No tool calls and no end_turn — return whatever text we have
                                                      return "\n".join(
                                                                            block.text for block in response.content if hasattr(block, "text")
                                                      )

            # Append assistant response and tool results, then loop
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return "Agent reached maximum iterations without a final response."


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------
if __name__ == "__main__":

      def get_weather(city: str) -> dict:
                """Get current weather for a city (mock implementation)."""
        mock_data = {
                      "new york": {"temp_f": 62, "condition": "Partly cloudy"},
                      "london": {"temp_f": 55, "condition": "Overcast"},
                      "tokyo": {"temp_f": 71, "condition": "Sunny"},
        }
        return mock_data.get(city.lower(), {"temp_f": 0, "condition": "Unknown city"})

    def calculate(expression: str) -> str:
              """Evaluate a mathematical expression safely."""
        allowed = set("0123456789+-*/.() ")
        if not all(ch in allowed for ch in expression):
                      return "Error: invalid characters in expression"
        try:
                      return str(eval(expression))  # noqa: S307
except Exception as e:
            return f"Error: {e}"

    agent = ToolUseAgent(tools=[get_weather, calculate])
    answer = agent.run("What is the weather in Tokyo? Also, what is 42 * 17?")
    print(answer)
