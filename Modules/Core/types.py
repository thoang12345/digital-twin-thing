from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(slots=True)
class ContextChunk:
    content: str
    source: str = "Unknown source"
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


