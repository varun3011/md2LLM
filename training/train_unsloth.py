"""
md2LLM Unsloth Training Script
For NVIDIA GPU with CUDA
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from training.trainer import get_hf_model_id, load_config, load_jsonl_dataset, prepare_texts, write_progress


def main():
    if len(sys.argv) < 2:
        print("Usage: python train_unsloth.py <config_path>")
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
                "message": "Loading Unsloth...",
            },
        )

        try:
            from datasets import Dataset as HFDataset
            from transformers import TrainerCallback, TrainingArguments
            from trl import SFTTrainer
            from unsloth import FastLanguageModel
        except ImportError as exc:
            raise ImportError("Unsloth not installed. Run: pip install unsloth") from exc

        hf_repo = config.get("hf_repo") or get_hf_model_id(config["model_name"])
        if not hf_repo:
            raise ValueError(f"Cannot find HuggingFace repo for {config['model_name']}")

        output_dir = config.get("output_path", f"models/{config['output_name']}")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        epochs = config.get("epochs", 3)
        lora_rank = config.get("lora_rank", 16)
        batch_size = config.get("batch_size", 2)
        learning_rate = float(config.get("learning_rate", "2e-4"))
        max_seq_length = config.get("max_seq_length", 2048)

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
            raise ValueError("No training data found")

        print(f"Loaded {len(texts)} training examples")

        write_progress(
            progress_file,
            {
                "progress": 10,
                "message": f"Loading {hf_repo} with 4-bit quantization...",
                "step": 0,
                "total_steps": 0,
                "loss": None,
            },
        )

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=hf_repo,
            max_seq_length=max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )

        model = FastLanguageModel.get_peft_model(
            model,
            r=lora_rank,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            lora_alpha=lora_rank * 2,
            lora_dropout=0.05,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=42,
        )

        hf_dataset = HFDataset.from_dict({"text": texts})

        grad_accum = 4
        effective_batch = batch_size * grad_accum
        steps_per_epoch = max(1, len(texts) // effective_batch)
        total_steps = steps_per_epoch * epochs

        write_progress(
            progress_file,
            {
                "progress": 15,
                "message": f"Starting training: {total_steps} steps, {epochs} epochs",
                "step": 0,
                "total_steps": total_steps,
                "loss": None,
            },
        )

        class ProgressCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                del args, control, kwargs
                if logs and state.global_step:
                    loss = logs.get("loss") or logs.get("train_loss")
                    pct = 15 + int((state.global_step / max(total_steps, 1)) * 75)
                    loss_value = round(float(loss), 4) if loss else None
                    write_progress(
                        progress_file,
                        {
                            "progress": min(90, pct),
                            "step": state.global_step,
                            "total_steps": total_steps,
                            "loss": loss_value,
                            "message": f"Step {state.global_step}/{total_steps} - loss: {loss_value or 'N/A'}",
                        },
                    )

        training_args = TrainingArguments(
            output_dir=str(Path(output_dir) / "checkpoints"),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            learning_rate=learning_rate,
            lr_scheduler_type="cosine",
            warmup_ratio=0.05,
            logging_steps=max(1, total_steps // 20),
            save_strategy="epoch",
            fp16=True,
            optim="adamw_8bit",
            seed=42,
            report_to="none",
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=hf_dataset,
            dataset_text_field="text",
            max_seq_length=max_seq_length,
            args=training_args,
            callbacks=[ProgressCallback()],
        )

        FastLanguageModel.for_training(model)
        trainer.train()

        write_progress(
            progress_file,
            {
                "progress": 92,
                "step": total_steps,
                "total_steps": total_steps,
                "loss": None,
                "message": "Saving model...",
            },
        )

        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

        write_progress(
            progress_file,
            {
                "progress": 95,
                "step": total_steps,
                "total_steps": total_steps,
                "loss": None,
                "message": "Converting to GGUF format...",
            },
        )

        gguf_path = f"{output_dir}.gguf"

        try:
            model.save_pretrained_gguf(output_dir, tokenizer, quantization_method="q4_k_m")
            gguf_files = list(Path(output_dir).glob("*.gguf"))
            if gguf_files:
                import shutil

                shutil.move(str(gguf_files[0]), gguf_path)
        except Exception as exc:
            print(f"GGUF export warning: {exc}")
            gguf_path = output_dir

        write_progress(
            progress_file,
            {
                "progress": 100,
                "step": total_steps,
                "total_steps": total_steps,
                "loss": None,
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
