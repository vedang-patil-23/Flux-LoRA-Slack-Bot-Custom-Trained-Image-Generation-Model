"""CLI helper to launch Flux LoRA training on Replicate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .replicate_client import ReplicateClient, zip_dataset

DEFAULT_MODEL_OWNER = "black-forest-labs"
DEFAULT_MODEL_NAME = "flux-lora-trainer"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a Flux LoRA on Replicate")
    parser.add_argument("--dataset-dir", type=Path, default=Path("ved"), help="Folder with childhood photos")
    parser.add_argument("--archive-path", type=Path, default=Path("artifacts/dataset.zip"), help="Temp zip archive path")
    parser.add_argument("--model-owner", default=os.getenv("REPLICATE_MODEL_OWNER", DEFAULT_MODEL_OWNER))
    parser.add_argument("--model-name", default=os.getenv("REPLICATE_MODEL_NAME", DEFAULT_MODEL_NAME))
    parser.add_argument("--max-train-steps", type=int, default=1200)
    parser.add_argument("--resolution", default="1024")
    parser.add_argument("--output-json", type=Path, default=Path("config/lora_version.json"))
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    api_token = os.getenv("REPLICATE_API_TOKEN")
    if not api_token:
        raise RuntimeError("REPLICATE_API_TOKEN missing")

    artifacts_dir = args.archive_path.parent
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    archive_path = zip_dataset(args.dataset_dir, args.archive_path)

    client = ReplicateClient(api_token)
    try:
        dataset_url = client.upload_dataset(archive_path)
        training = client.start_training(
            model_owner=args.model_owner,
            model_name=args.model_name,
            input_params={
                "input_images": dataset_url,
                "resolution": args.resolution,
                "max_train_steps": args.max_train_steps,
            },
        )
        training_id = training["id"]
        print(f"Started training: {training_id}")
        final_state = client.poll_training(training_id)
        status = final_state["status"]
        print(f"Training finished with status: {status}")
        if status != "succeeded":
            raise RuntimeError(f"Training failed: {json.dumps(final_state, indent=2)}")

        lora_version = final_state["output"]["version"]
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps({"lora_version": lora_version}, indent=2))
        print(f"Wrote LoRA version id to {args.output_json}")
    finally:
        client.close()


if __name__ == "__main__":
    main()


