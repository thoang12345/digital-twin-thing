import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(slots=True)
class ToolTraceItem:
    round_number: int
    tool_name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]
    error: Optional[str] = None


@dataclass(slots=True)
class ToolLoopResult:
    final_response: str
    finished: bool
    rounds_used: int
    messages: List[Dict[str, Any]]
    tool_trace: List[ToolTraceItem] = field(default_factory=list)
    error: Optional[str] = None


class ToolLoopRunner:
    def __init__(
        self,
        client,
        model: str,
        tools: List[Dict[str, Any]],
        tool_registry: Dict[str, Callable[..., Dict[str, Any]]],
        max_tool_rounds: int = 10,
        temperature: float = 0.0,
        finish_tool_name: str = "finish",
        require_tool_choice: bool = True,
        debug: bool = False,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.client = client
        self.model = model
        self.tools = tools
        self.tool_registry = tool_registry
        self.max_tool_rounds = max_tool_rounds
        self.temperature = temperature
        self.finish_tool_name = finish_tool_name
        self.require_tool_choice = require_tool_choice
        self.debug = debug
        self.event_callback = event_callback

    def run(self, initial_messages: List[Dict[str, Any]]) -> ToolLoopResult:
        working_messages = list(initial_messages)
        tool_trace: List[ToolTraceItem] = []
        last_error = None

        for round_number in range(1, self.max_tool_rounds + 1):
            self._emit_event("round_started", round_number=round_number)
            if self.debug:
                print(f"\n-- Tool Round {round_number} --")

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=working_messages,
                    tools=self.tools,
                    tool_choice="required" if self.require_tool_choice else "auto",
                    temperature=self.temperature,
                )
            except Exception as exc:
                return ToolLoopResult(
                    final_response="",
                    finished=False,
                    rounds_used=round_number - 1,
                    messages=working_messages,
                    tool_trace=tool_trace,
                    error=f"Model call failed: {exc}",
                )
                self._emit_event(
                    "model_error",
                    round_number=round_number,
                    error=result.error,
                )
                self._emit_event(
                    "loop_finished",
                    finished=False,
                    rounds_used=result.rounds_used,
                    error=result.error,
                    final_response=result.final_response,
                )
                return result
            msg = response.choices[0].message
            tool_calls = list(getattr(msg, "tool_calls", []) or [])
            self._emit_event(
                "model_message",
                round_number=round_number,
                content=msg.content or "",
                tool_calls=[
                    {
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    }
                    for tool_call in tool_calls
                ],
            )

            if not tool_calls:
                content = msg.content or ""
                working_messages.append({"role": "assistant", "content": content})
                result = ToolLoopResult(
                    final_response=content,
                    finished=True,
                    rounds_used=round_number,
                    messages=working_messages,
                    tool_trace=tool_trace,
                    error=last_error,
                )
                self._emit_event(
                    "assistant_response",
                    round_number=round_number,
                    content=content,
                )
                self._emit_event(
                    "loop_finished",
                    finished=result.finished,
                    rounds_used=result.rounds_used,
                    error=result.error,
                    final_response=result.final_response,
                )
                return result

            assistant_message = self._build_assistant_tool_message(msg)
            working_messages.append(assistant_message)

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_args, parse_error = self._parse_tool_arguments(
                    tool_call.function.arguments
                )
                self._emit_event(
                    "tool_started",
                    round_number=round_number,
                    tool_name=tool_name,
                    arguments=tool_args,
                    raw_arguments=tool_call.function.arguments,
                )

                if parse_error:
                    tool_result = {"error": parse_error}
                    last_error = parse_error
                else:
                    tool_result = self._execute_tool(tool_name=tool_name, tool_args=tool_args)
                    if "error" in tool_result:
                        last_error = tool_result["error"]

                working_messages.append(
                    self._build_tool_result_message(
                        tool_call_id=tool_call.id,
                        tool_result=tool_result,
                    )
                )

                trace_item = ToolTraceItem(
                    round_number=round_number,
                    tool_name=tool_name,
                    arguments=tool_args,
                    result=tool_result,
                    error=tool_result.get("error"),
                )
                tool_trace.append(trace_item)
                self._emit_event(
                    "tool_finished",
                    round_number=round_number,
                    tool_name=tool_name,
                    arguments=tool_args,
                    result=tool_result,
                    error=tool_result.get("error"),
                )

                if self.debug:
                    print("Tool:", tool_name)
                    print("Args:", tool_args)
                    print("Result:", tool_result)

                if tool_name == self.finish_tool_name and "final_response" in tool_result:
                    result = ToolLoopResult(
                        final_response=tool_result["final_response"],
                        finished=True,
                        rounds_used=round_number,
                        messages=working_messages,
                        tool_trace=tool_trace,
                        error=None,
                    )
                    self._emit_event(
                        "loop_finished",
                        finished=result.finished,
                        rounds_used=result.rounds_used,
                        error=result.error,
                        final_response=result.final_response,
                    )
                    return result

        result = ToolLoopResult(
            final_response="",
            finished=False,
            rounds_used=self.max_tool_rounds,
            messages=working_messages,
            tool_trace=tool_trace,
            error=last_error or "Stopped after too many tool rounds.",
        )
        self._emit_event(
            "loop_finished",
            finished=result.finished,
            rounds_used=result.rounds_used,
            error=result.error,
            final_response=result.final_response,
        )
        return result

    def _build_assistant_tool_message(self, msg) -> Dict[str, Any]:
        assistant_message = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [],
        }

        for tool_call in msg.tool_calls:
            assistant_message["tool_calls"].append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
            )

        return assistant_message

    def _build_tool_result_message(
        self,
        tool_call_id: str,
        tool_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(tool_result),
        }

    def _parse_tool_arguments(
        self,
        arguments: Optional[str],
    ) -> tuple[Dict[str, Any], Optional[str]]:
        try:
            return json.loads(arguments or "{}"), None
        except json.JSONDecodeError:
            return {}, "Invalid JSON arguments from model."

    def _execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        fn = self.tool_registry.get(tool_name)
        if fn is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = fn(**tool_args)
        except Exception as exc:
            return {"error": str(exc)}

        if isinstance(result, dict):
            return result

        return {"result": result}

    def set_event_callback(
        self,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> None:
        self.event_callback = event_callback

    def _emit_event(self, event_type: str, **payload: Any) -> None:
        if self.event_callback is None:
            return
        self.event_callback({"type": event_type, **payload})


