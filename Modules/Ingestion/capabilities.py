from __future__ import annotations

import importlib.util
from pathlib import Path

from Modules.Ingestion.types import RuntimeCapabilities


class RuntimeCapabilitiesProbe:
    def __init__(self, huggingface_cache_root: Path | None = None) -> None:
        if huggingface_cache_root is None:
            huggingface_cache_root = Path.home() / ".cache" / "huggingface" / "hub"
        self.huggingface_cache_root = huggingface_cache_root

    def detect(self) -> RuntimeCapabilities:
        docling_available = self._module_available("docling.document_converter")
        pdfium_available = self._module_available("pypdfium2")
        pypdf_available = self._module_available("pypdf")
        docx_available = self._module_available("docx")
        local_docling_cache = self._has_docling_layout_cache()

        notes = []
        if docling_available and local_docling_cache:
            notes.append("Docling imports and local layout-model cache are available.")
        elif docling_available:
            notes.append("Docling imports are available, but local layout-model cache was not confirmed.")
        if pdfium_available or pypdf_available:
            notes.append("A local PDF text extractor is available.")

        return RuntimeCapabilities(
            docling_import_available=docling_available,
            local_docling_model_cache_available=local_docling_cache,
            pdf_text_extractor_available=pdfium_available or pypdf_available,
            docx_support_available=docx_available,
            tokenizer_fallback_available=True,
            notes=notes,
        )

    @staticmethod
    def _module_available(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except ModuleNotFoundError:
            return False

    def _has_docling_layout_cache(self) -> bool:
        if not self.huggingface_cache_root.exists():
            return False

        patterns = (
            "models--docling-project--docling-layout-*",
            "models--docling-project--docling-ocr-*",
        )
        for pattern in patterns:
            for model_dir in self.huggingface_cache_root.glob(pattern):
                snapshots_dir = model_dir / "snapshots"
                if not snapshots_dir.exists():
                    continue
                for snapshot_dir in snapshots_dir.iterdir():
                    if snapshot_dir.is_dir() and any(snapshot_dir.iterdir()):
                        return True
        return False
