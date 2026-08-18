from typing import Dict, List, Optional

from Modules.Core.types import ContextChunk


DEFAULT_SYSTEM_PROMPT = "\n".join(
    [
        "You are an expert tool-calling assistant for digital twin models.",
        "These twins represent a physical system where a battery interfaces with a load bus through a boost converter.",
        "The only live sensor values from the physical system are load_side_current_converter and converter_temperature.",
        "The user is giving you permission to use tools whenever needed to answer their request.",
        "Before acting, classify the request into one of four intents:",
        "1. STATUS QUERY: the user is asking about the current state of a digital twin. Only call get_DT_state and finish. Do not activate anything.",
        "2. EXPLICIT ACTIVATION: the user directly requests activation or deactivation. Resolve dependencies and activate in the correct order. Check whether required inputs are available before activating a model.",
        "3. OUTPUT REQUEST: the user asks for a value or signal that requires a digital twin to compute. Identify which digital twin produces that output, resolve dependencies, activate required models, then answer the request.",
        "4. AUTONOMOUS DT RUN: the user asks to run, supervise, control, test, or evaluate the battery/load-bus autonomous digital twin mission. Use run_autonomous_DT with bounded mission settings, then summarize the status and artifact paths.",
        "Do not activate any digital twin unless the request is an explicit activation or output request.",
        "Do not run the autonomous DT mission unless the request asks for a run, control action, simulation trial, UDP live trial, report generation, or mission evaluation.",
        "For run_autonomous_DT, prefer backend='mock' for quick sanity checks, backend='simulink' only when MATLAB Engine should advance the model, and backend='udp' only when the live Simulink model is already running.",
        "Do not ask the user for clarification if a reasonable search can be performed first. Use the tools to investigate.",
        "Call the finish tool to produce the final response.",
        "For general greetings, respond by calling finish directly.",
        "Do not guess tool results.",
    ]
)


class PromptBuilder:
    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_memory_messages: int = 5,
        max_rag_chunks: int = 5,
    ):
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_memory_messages = max_memory_messages
        self.max_rag_chunks = max_rag_chunks

    def format_rag_context(self, rag_matches: List[ContextChunk]) -> str:
        if not rag_matches:
            return ""

        selected_matches = rag_matches[: self.max_rag_chunks]
        formatted_chunks = []

        for index, match in enumerate(selected_matches, start=1):
            chunk_text = [f"[Context {index}]", f"Source: {match.source}"]
            if match.score is not None:
                chunk_text.append(f"Similarity score: {match.score:.4f}")
            chunk_text.append("Content:")
            chunk_text.append(match.content.strip())
            formatted_chunks.append("\n".join(chunk_text))

        return "\n\n".join(formatted_chunks)

    def trim_memory(self, chat_memory: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if not chat_memory:
            return []
        return chat_memory[-self.max_memory_messages :]

    def build_user_prompt(self, user_query: str, rag_context: str) -> str:
        if not rag_context:
            return user_query

        return "\n\n".join(
            [
                f"User request:\n{user_query}",
                f"Retrieved context:\n{rag_context}",
            ]
        )

    def build_payload(
        self,
        user_query: str,
        rag_matches: Optional[List[ContextChunk]] = None,
        chat_memory: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        rag_matches = rag_matches or []
        chat_memory = chat_memory or []

        rag_context = self.format_rag_context(rag_matches)
        trimmed_memory = self.trim_memory(chat_memory)

        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(trimmed_memory)
        messages.append(
            {
                "role": "user",
                "content": self.build_user_prompt(user_query, rag_context),
            }
        )
        return messages
