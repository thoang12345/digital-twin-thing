from openai import OpenAI

from Modules.Chat_Memory.Chat_Memory import ChatMemory
from Modules.Core.conversationloop import ConversationLoop
from Modules.Core.settings import AgentSettings
from Modules.Prompt.prompt import PromptBuilder
from Modules.RAG.Retriever import ChromaRAGRetriever
from Modules.Tools.Tool_loop import ToolLoopRunner
from Modules.Tools.dt_state import DTStateManager
from Modules.Tools.search_tools import ChromaToolSearch
from Modules.Tools.tool_catalog import build_default_toolset
from Modules.adapters.rag_adapters import search_result_to_context_chunks


def build_conversation(settings: AgentSettings | None = None) -> ConversationLoop:
    settings = settings or AgentSettings()

    client = OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
    )
    prompt_builder = PromptBuilder(
        max_memory_messages=settings.max_memory_messages,
        max_rag_chunks=settings.max_rag_chunks,
    )
    rag_retriever = ChromaRAGRetriever(
        collection_name=settings.rag_collection_name,
        persist_directory=settings.chroma_persist_directory,
    )
    chat_memory = ChatMemory(max_messages=settings.chat_memory_limit)
    dt_state_manager = DTStateManager()
    chroma_tools = ChromaToolSearch(
        persist_directory=settings.chroma_persist_directory,
    )
    tools, tool_registry = build_default_toolset(dt_state_manager, chroma_tools)
    tool_loop_runner = ToolLoopRunner(
        client=client,
        model=settings.model,
        tools=tools,
        tool_registry=tool_registry,
        max_tool_rounds=settings.max_tool_rounds,
        temperature=settings.temperature,
        debug=settings.debug,
    )

    conversation = ConversationLoop(
        prompt_builder=prompt_builder,
        tool_loop_runner=tool_loop_runner,
        chat_memory=chat_memory,
        rag_retriever=rag_retriever,
        rag_adapter=search_result_to_context_chunks,
        rag_top_k=settings.rag_top_k,
        debug=settings.debug,
    )

    conversation.database_browser = chroma_tools
    conversation.available_tools = tools
    conversation.available_tool_registry = tool_registry
    conversation.agent_settings = settings

    return conversation
