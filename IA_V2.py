import argparse

from Modules.Core.bootstrap import build_conversation
from Modules.Core.settings import AgentSettings


def parse_args() -> AgentSettings:
    defaults = AgentSettings()
    parser = argparse.ArgumentParser(
        description="Run the modular digital twin assistant."
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

    print("Digital twin assistant V2")
    print("Type 'quit', 'exit', or 'q' to stop.")

    while True:
        user_query = input("\nUser: ").strip()

        if user_query.lower() in {"exit", "quit", "q"}:
            print("Exiting.")
            break

        if not user_query:
            continue

        result = conversation.run_turn(user_query)

        print("\nAssistant:")
        print(result["final_response"])

        if not result["finished"] and result["error"]:
            print("\nError:")
            print(result["error"])


if __name__ == "__main__":
    main()
