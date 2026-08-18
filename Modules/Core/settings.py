from dataclasses import dataclass


@dataclass(slots=True)
class AgentSettings:
    model: str = "llama-3-groq-8b-tool-use"
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    chroma_persist_directory: str = "./chroma_db"
    rag_collection_name: str = "rag_collection"
    max_memory_messages: int = 10
    max_rag_chunks: int = 5
    chat_memory_limit: int = 20
    max_tool_rounds: int = 10
    rag_top_k: int = 5
    temperature: float = 0.0
    debug: bool = False
