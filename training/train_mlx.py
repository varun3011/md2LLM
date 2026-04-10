"""
md2LLM MLX Training Script
For Mac Apple Silicon (M1/M2/M3)
"""

import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from training.trainer import get_hf_model_id, load_config, load_jsonl_dataset, prepare_texts, write_progress


def verify_mlx_runtime():
    """
    Import MLX in a child process so native Metal initialization crashes
    can be reported clearly by the parent process.
    """
    if sys.version_info >= (3, 14):
        raise RuntimeError(
            "MLX is installed, but this project is running with Python "
            f"{platform.python_version()}. The installed MLX wheel is crashing "
            "during Metal initialization on this Python version. Use a Python "
            "3.12 or 3.13 virtual environment, then reinstall requirements and "
            "mlx-lm in that environment."
        )

    result = subprocess.run(
        [sys.executable, "-c", "import mlx.core; import mlx_lm"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if len(detail) > 1600:
            detail = f"{detail[:800]}\n...\n{detail[-800:]}"
        raise RuntimeError(
            "MLX is installed, but it failed to initialize in this Python "
            f"environment. Details: {detail}"
        )


def main():
    if len(sys.argv) < 2:
        print("Usage: python train_mlx.py <config_path>")
        sys.exit(1)

    config_path = sys.argv[1]
    config = load_config(config_path)
    progress_file = config.get("progress_file", "/tmp/train_progress.json")

    try:
        write_progress(
            progress_file,
            {
                "progress": 5,
                "step": 0,
                "total_steps": 0,
                "loss": None,
                "message": "Loading MLX and model...",
            },
        )

        try:
            verify_mlx_runtime()

            import mlx.optimizers as optim
            from mlx_lm import load
            from mlx_lm.tuner.callbacks import TrainingCallback
            from mlx_lm.tuner.datasets import CacheDataset, TextDataset
            from mlx_lm.tuner.trainer import TrainingArgs, train
            from mlx_lm.tuner.utils import linear_to_lora_layers
        except ImportError as exc:
            raise ImportError(
                "MLX import failed. If mlx-lm is installed, this is likely an "
                f"mlx-lm API/version mismatch or environment issue: {exc}"
            ) from exc

        hf_repo = config.get("hf_repo") or get_hf_model_id(config["model_name"])
        if not hf_repo:
            raise ValueError(f"Cannot find HuggingFace repo for {config['model_name']}")

        output_dir = config.get("output_path", f"models/{config['output_name']}")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        write_progress(
            progress_file,
            {
                "progress": 8,
                "message": "Loading training dataset...",
                "step": 0,
                "total_steps": 0,
                "loss": None,
            },
        )

        pairs = load_jsonl_dataset(config["data_file"], config["goal"])
        texts = prepare_texts(pairs, config["goal"])

        if not texts:
            raise ValueError("No training data found in the dataset file")

        print(f"Loaded {len(texts)} training examples")

        split = int(len(texts) * 0.9)
        train_texts = texts[:split]
        valid_texts = texts[split:] or texts[:5]

        write_progress(
            progress_file,
            {
                "progress": 10,
                "message": f"Loading {hf_repo}...",
                "step": 0,
                "total_steps": 0,
                "loss": None,
            },
        )

        model, tokenizer = load(hf_repo)

        epochs = config.get("epochs", 3)
        lora_rank = config.get("lora_rank", 16)
        batch_size = config.get("batch_size", 2)
        learning_rate = float(config.get("learning_rate", "2e-4"))
        max_seq_length = config.get("max_seq_length", 2048)

        batch_size = max(1, min(batch_size, len(train_texts)))
        if len(valid_texts) < batch_size:
            valid_texts = train_texts[:batch_size]

        steps_per_epoch = max(1, len(train_texts) // batch_size)
        total_steps = steps_per_epoch * epochs

        write_progress(
            progress_file,
            {
                "progress": 12,
                "message": f"Starting training: {total_steps} steps, {epochs} epochs",
                "step": 0,
                "total_steps": total_steps,
                "loss": None,
            },
        )

        last_loss = [None]

        class ProgressCallback(TrainingCallback):
            def on_train_loss_report(self, train_info: dict):
                step = int(train_info.get("iteration", 0))
                loss = train_info.get("train_loss")
                last_loss[0] = round(float(loss), 4) if loss is not None else None
                pct = 12 + int((step / max(total_steps, 1)) * 80)
                write_progress(
                    progress_file,
                    {
                        "progress": min(92, pct),
                        "step": step,
                        "total_steps": total_steps,
                        "loss": last_loss[0],
                        "message": f"Training step {step}/{total_steps} - loss: {last_loss[0]}",
                    },
                )

        train_dataset = CacheDataset(
            TextDataset(data=[{"text": text} for text in train_texts], tokenizer=tokenizer)
        )
        valid_dataset = CacheDataset(
            TextDataset(data=[{"text": text} for text in valid_texts], tokenizer=tokenizer)
        )

        model.freeze()
        num_lora_layers = min(16, len(getattr(model, "layers", [])))
        if num_lora_layers <= 0:
            raise ValueError("Loaded MLX model does not expose transformer layers for LoRA training")

        lora_parameters = {
            "rank": lora_rank,
            "dropout": 0.0,
            "scale": lora_rank * 2,
        }
        linear_to_lora_layers(
            model,
            num_lora_layers,
            lora_parameters,
        )

        adapter_file = Path(output_dir) / "adapters.safetensors"
        with (Path(output_dir) / "adapter_config.json").open("w") as handle:
            json.dump(
                {
                    "model": hf_repo,
                    "fine_tune_type": "lora",
                    "num_layers": num_lora_layers,
                    "lora_parameters": lora_parameters,
                    "max_seq_length": max_seq_length,
                },
                handle,
                indent=2,
            )

        training_args = TrainingArgs(
            batch_size=batch_size,
            iters=total_steps,
            val_batches=max(1, len(valid_texts) // batch_size),
            steps_per_report=max(1, total_steps // 20),
            steps_per_eval=max(1, total_steps // 5),
            steps_per_save=max(1, total_steps),
            adapter_file=str(adapter_file),
            max_seq_length=max_seq_length,
            grad_checkpoint=True,
        )
        optimizer = optim.Adam(learning_rate=learning_rate)

        train(
            model=model,
            optimizer=optimizer,
            args=training_args,
            train_dataset=train_dataset,
            val_dataset=valid_dataset,
            training_callback=ProgressCallback(),
        )

        write_progress(
            progress_file,
            {
                "progress": 93,
                "step": total_steps,
                "total_steps": total_steps,
                "loss": last_loss[0],
                "message": "Saving model and converting to GGUF...",
            },
        )

        gguf_path = f"{output_dir}.gguf"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "mlx_lm.fuse",
                "--model",
                hf_repo,
                "--adapter-path",
                output_dir,
                "--save-path",
                f"{output_dir}_merged",
                "--export-gguf",
            ],
            check=False,
        )

        merged_gguf = Path(f"{output_dir}_merged") / "model.gguf"
        if merged_gguf.exists():
            import shutil

            shutil.move(str(merged_gguf), gguf_path)
        else:
            gguf_path = output_dir

        write_progress(
            progress_file,
            {
                "progress": 100,
                "step": total_steps,
                "total_steps": total_steps,
                "loss": last_loss[0],
                "message": f"Training complete! Model saved to {gguf_path}",
                "output_path": gguf_path,
            },
        )

    except Exception as exc:
        write_progress(
            progress_file,
            {
                "progress": 0,
                "step": 0,
                "total_steps": 0,
                "loss": None,
                "message": f"Training failed: {str(exc)}",
                "error": str(exc),
            },
        )
        print(f"Training failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
