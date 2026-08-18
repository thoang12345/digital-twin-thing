from typing import Any, Callable, Dict, List, Optional

from Modules.Core.types import ContextChunk


class ConversationLoop:
    def __init__(
        self,
        prompt_builder,
        tool_loop_runner,
        chat_memory,
        rag_retriever=None,
        rag_adapter: Optional[Callable[[Any], List[ContextChunk]]] = None,
        rag_top_k: int = 5,
        debug: bool = False,
    ):
        self.prompt_builder = prompt_builder
        self.tool_loop_runner = tool_loop_runner
        self.chat_memory = chat_memory
        self.rag_retriever = rag_retriever
        self.rag_adapter = rag_adapter
        self.rag_top_k = rag_top_k
        self.debug = debug

    def run_turn(self, user_query: str) -> Dict[str, Any]:
        rag_matches = self._get_rag_context(user_query)
        chat_history = self.chat_memory.get_messages()

        initial_messages = self.prompt_builder.build_payload(
            user_query=user_query,
            rag_matches=rag_matches,
            chat_memory=chat_history,
        )

        if self.debug:
            print("\n== Initial Messages Sent To Tool Loop ==")
            for index, message in enumerate(initial_messages, start=1):
                print("=" * 80)
                print(f"Message {index}")
                print("Role:", message.get("role"))
                print("Content:")
                print(message.get("content"))

        tool_result = self.tool_loop_runner.run(initial_messages)
        final_response = tool_result.final_response

        if not tool_result.finished and not final_response:
            final_response = (
                "I was unable to complete the request because the tool loop did not finish."
            )

        self.chat_memory.add_user_message(user_query)
        self.chat_memory.add_assistant_message(final_response)

        return {
            "final_response": final_response,
            "finished": tool_result.finished,
            "error": tool_result.error,
            "rounds_used": tool_result.rounds_used,
            "rag_matches": rag_matches,
            "initial_messages": initial_messages,
            "working_messages": tool_result.messages,
            "tool_trace": tool_result.tool_trace,
        }

    def _get_rag_context(self, user_query: str) -> List[ContextChunk]:
        if self.rag_retriever is None:
            return []

        try:
            search_result = self.rag_retriever.search(
                query=user_query,
                top_k=self.rag_top_k,
            )
        except Exception as exc:
            if self.debug:
                print(f"RAG retrieval failed: {exc}")
            return []

        if self.rag_adapter is None:
            return [
                ContextChunk(
                    content=match.content,
                    source=match.metadata.get("source", match.id),
                    score=match.score,
                    metadata=match.metadata,
                )
                for match in search_result.matches
            ]

        try:
            return self.rag_adapter(search_result)
        except Exception as exc:
            if self.debug:
                print(f"RAG adapter failed: {exc}")
            return []
