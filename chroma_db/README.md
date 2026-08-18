# Runtime RAG Store

This directory intentionally starts empty. The assistant creates its Chroma
database here when documents or notes are ingested on the deployment machine.

The prior development database was not included because its metadata contained
machine-specific source paths. Excluding it keeps the handoff portable and does
not remove any agent or retrieval functionality.

