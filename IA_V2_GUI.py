import argparse
import tkinter as tk

from Modules.Core.bootstrap import build_conversation
from Modules.Core.settings import AgentSettings
from Modules.GUI.app import AssistantGuiApp


def parse_args() -> AgentSettings:
    defaults = AgentSettings()
    parser = argparse.ArgumentParser(
        description="Run the digital twin assistant GUI."
    )
    parser.add_argument("--model", default=defaults.model)
    parser.add_argument("--base-url", default=defaults.base_url)
    parser.add_argument("--api-key", default=defaults.api_key)
    parser.add_argument(
        "--chroma-path",
        default=defaults.chroma_persist_directory,
        help="Path to the Chroma persistence directory.",
    )
    parser.add_argument("--rag-collection", default=defaults.rag_collection_name)
    parser.add_argument("--debug", action="store_true", default=defaults.debug)
    args = parser.parse_args()

    return AgentSettings(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        chroma_persist_directory=args.chroma_path,
        rag_collection_name=args.rag_collection,
        debug=args.debug,
    )


def main() -> None:
    settings = parse_args()
    conversation = build_conversation(settings)

    root = tk.Tk()
    AssistantGuiApp(root, conversation)
    root.mainloop()


if __name__ == "__main__":
    main()
