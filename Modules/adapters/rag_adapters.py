from typing import List

from Modules.Core.types import ContextChunk


def search_result_to_context_chunks(search_result) -> List[ContextChunk]:
    chunks = []
    for match in search_result.matches:
        source = match.metadata.get("source", match.id)
        chunks.append(
            ContextChunk(
                content=match.content,
                source=source,
                score=match.score,
                metadata=match.metadata,
            )
        )
    return chunks
