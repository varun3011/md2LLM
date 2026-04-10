from __future__ import annotations

import argparse

from pipeline.data_generator import generate_training_data
from pipeline.utils import load_config, load_environment
from pipeline.vault_reader import read_vault


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fine-tuning data from your Obsidian vault")
    parser.add_argument("--vault", help="Path to vault folder")
    parser.add_argument("--goal", choices=["knowledge", "style", "reasoning", "chatbot"])
    parser.add_argument("--model")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--min-quality", type=float)
    parser.add_argument("--output", help="Path to output JSONL file")
    parser.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Run LLM quality validation on each generated pair (slower but higher quality)"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        default=False,
        help="Start fresh and ignore existing checkpoint"
    )
    args = parser.parse_args()

    load_environment()
    config = load_config(args.config) if args.config else {}
    vault_config = config.get("vault", {})
    training_config = config.get("training", {})

    vault_path = args.vault or vault_config.get("path")
    if not vault_path:
        raise ValueError("A vault path is required. Pass --vault or provide it in config.yaml")

    goal = args.goal or training_config.get("goal", "knowledge")
    model = args.model or training_config.get("model", "gpt-4o-mini")
    min_quality = args.min_quality if args.min_quality is not None else vault_config.get("min_quality", 0.4)
    output_path = args.output or training_config.get("output_path", "output/training_data.jsonl")

    print("md2LLM — Turn your notes into your personal model")
    print("─────────────────────────────────────────────────")

    print("\n[1/2] Reading Vault")
    print(f"Vault: {vault_path}")
    notes = read_vault(vault_path, min_quality=min_quality)

    print("\n[2/2] Generating Training Data")
    stats = generate_training_data(
        notes=notes,
        goal=goal,
        model=model,
        output_path=output_path,
        resume=not args.no_resume,
        use_llm_validation=args.validate,
    )

    print(f"\nDone! {stats['total_pairs']} training pairs saved to {output_path}")


if __name__ == "__main__":
    main()
