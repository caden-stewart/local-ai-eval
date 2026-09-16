"""A deliberately plain tool-calling loop.

No agent framework: a framework's own retries, prompt templates and parsing
quirks would become part of what gets measured. This is the minimum loop every
framework is built on, so the results reflect the model.

    ask the model -> it asks for tools -> run them -> hand back results -> repeat
    until it answers without asking for a tool, or runs out of steps.
"""
from __future__ import annotations

import json
from typing import Any, Callable


def run_agent(
    chat: Callable[..., dict[str, Any]],
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    handle_tool: Callable[[str, dict[str, Any]], Any],
    max_steps: int = 15,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    calls: list[dict[str, Any]] = []

    for step in range(1, max_steps + 1):
        reply = chat(messages, tools=tools)
        message = reply["message"]
        tool_calls = message.get("tool_calls") or []

        assistant: dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        messages.append(assistant)

        if not tool_calls:
            return {
                "final_text": message.get("content") or "",
                "calls": calls,
                "steps": step,
                "stopped": "finished",
            }

        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = function.get("name", "")
            raw_args = function.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except ValueError:
                # A model that emits broken JSON gets told so and can retry;
                # the malformed call still counts against it in the transcript.
                result: Any = {"error": "arguments were not a valid JSON object"}
                calls.append({"name": name, "args": None, "raw_args": raw_args, "result": result})
            else:
                result = handle_tool(name, args)
                calls.append({"name": name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": json.dumps(result),
            })

    return {"final_text": "", "calls": calls, "steps": max_steps, "stopped": "max_steps"}
