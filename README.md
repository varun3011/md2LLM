# md2LLM

Turn your markdown notes into a small local model you can chat with.

`md2LLM` reads an Obsidian vault or any folder of Markdown files, scores the notes, generates fine-tuning data, recommends a training path based on your hardware, and helps you run the resulting model locally with Ollama.

[Overview](#overview) • [Features](#features) • [Getting Started](#getting-started) • [Run The App](#run-the-app) • [Workflow](#workflow) • [Training Options](#training-options) • [Project Structure](#project-structure) • [Troubleshooting](#troubleshooting)

> [!TIP]
> You can use the full browser workflow, or generate `training_data.jsonl` from the CLI with `python -m pipeline.main`.

## Overview

The project is split into three stages:

```text
Markdown notes
    |
    v
Training data generation
    |
    v
Fine-tuning on MLX / Unsloth / Colab
    |
    v
Local chat through Ollama
```

Typical flow:

1. Select a vault, folder upload, zip archive, or an existing `training_data.jsonl` file.
2. Choose the training goal: `knowledge`, `style`, `reasoning`, or `chatbot`.
3. Generate JSONL examples from your notes using an LLM provider.
4. Pick a base model from the recommended Hugging Face repos.
5. Fine-tune locally on Apple Silicon with MLX, on NVIDIA with Unsloth, or use the Colab fallback.
6. Export or load the trained model and chat with it locally.

## Features

- Browser-based workflow for vault upload, note review, generation, training, and chat
- Markdown parsing with frontmatter, tags, wikilinks, and note quality scoring
- Four dataset generation modes for different personalization goals
- Hardware-aware training recommendations
- Local training support for Apple Silicon and NVIDIA GPUs
- Google Colab fallback for low-memory or CPU-only machines
- Ollama integration for model discovery and local chat
- CLI entry point for dataset generation without the frontend

## Getting Started

### Prerequisites

You need:

- Python `3.10+`
- Node.js `18+`
- Ollama installed locally for chat and local model usage
- An `OPENAI_API_KEY` for the default data-generation path

Recommended hardware:

- Apple Silicon Mac with `16 GB+` RAM for MLX training
- NVIDIA GPU with CUDA for Unsloth training
- Low-memory or CPU-only machines should expect to use the Colab path

### Install Dependencies

```bash
git clone <your-repo-url>
cd ownLLM

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Install the training backend that matches your machine:

```bash
# Apple Silicon
pip install -r requirements-mlx.txt

# NVIDIA GPU
pip install -r requirements-unsloth.txt
```

> [!IMPORTANT]
> `requirements-unsloth.txt` assumes CUDA-compatible PyTorch is already installed. The comments in that file call this out explicitly.

### Configure Environment

```bash
cp .env.example .env
```

At minimum, set:

```bash
OPENAI_API_KEY=your-openai-api-key-here
```

Optional:

- Set `HF_TOKEN` if you want to train gated Hugging Face models such as Llama 3.2.
- Use an Ollama model for data generation from the UI instead of OpenAI if you want a local generation path.

## Run The App

### Development Mode

Start the FastAPI backend:

```bash
python -m server.app
```

In a second terminal, start the Vite frontend:

```bash
cd frontend
npm run dev
```

Then open:

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

### Production-Like Local Run

Build the frontend and let FastAPI serve it:

```bash
cd frontend
npm run build
cd ..
python -m server.app
```

Open `http://localhost:8000`.

## Workflow

### 1. Select Your Input

The app accepts:

- A vault path on disk
- A zipped vault upload
- A folder upload from the browser
- An existing `training_data.jsonl` file if you already generated data elsewhere

The backend registers the vault, scans Markdown files, and stores job state under `output/` and `uploads/`.

### 2. Configure Data Generation

Generation supports four goals:

| Goal | What it optimizes for |
| --- | --- |
| `knowledge` | Answering questions about what is in your notes |
| `style` | Reproducing your writing voice |
| `reasoning` | Connecting ideas the way your notes do |
| `chatbot` | Producing conversational first-person responses |

By default, the app uses `gpt-4o-mini` for training data generation, but the UI also supports choosing another provider/model string.

### 3. Review Notes And Generate JSONL

The pipeline:

- reads Markdown files recursively
- skips excluded folders such as `.obsidian`, `_templates`, `templates`, `attachments`, and `assets`
- scores notes based on length, metadata, links, tags, and draft/raw markers
- generates training pairs and streams progress back to the UI

Generated datasets are written to `output/` and can be downloaded from the app.

### 4. Train A Base Model

The training flow checks:

- hardware capabilities
- whether the selected Hugging Face model is already cached locally
- whether a Hugging Face token is required

From there the app routes you to the best path for your machine.

## Training Options

### Apple Silicon

Uses `training/train_mlx.py` and exports a GGUF model after MLX LoRA fine-tuning.

Notes:

- Best experience is on Apple Silicon with `16 GB+` RAM
- The MLX script explicitly warns against problematic Python environments
- If memory is too tight, the app recommends Colab instead of forcing local training

### NVIDIA GPU

Uses `training/train_unsloth.py` for 4-bit LoRA fine-tuning with Unsloth and then attempts GGUF export.

Notes:

- Best suited to CUDA-capable machines
- Larger models may still require significant VRAM
- Gated models may require `HF_TOKEN`

### Google Colab

The fallback notebook lives at [training/md2LLM_colab.ipynb](/Users/csuftitan/Desktop/ownLLM/training/md2LLM_colab.ipynb).

This path is recommended when:

- no suitable local GPU is available
- RAM is too limited for a safe local run
- you want a predictable training environment without local ML dependencies

### Supported Training Repos

The UI recommends curated Hugging Face models such as:

- `Qwen/Qwen2.5-1.5B-Instruct`
- `Qwen/Qwen2.5-3B-Instruct`
- `Qwen/Qwen2.5-7B-Instruct`
- `microsoft/Phi-3-mini-4k-instruct`
- `meta-llama/Llama-3.2-1B-Instruct`
- `meta-llama/Llama-3.2-3B-Instruct`

After training, models are stored under `models/`, and local chat uses the Ollama API.

## CLI Usage

If you only want to generate the dataset:

```bash
python -m pipeline.main \
  --vault /path/to/your/vault \
  --goal knowledge \
  --model gpt-4o-mini \
  --output output/training_data.jsonl
```

Useful flags:

- `--validate` to run LLM quality validation on generated pairs
- `--no-resume` to ignore any existing checkpoint and start fresh
- `--min-quality` to override the default note threshold

## Project Structure

```text
frontend/    React + Vite app for the end-to-end workflow
server/      FastAPI app, routes, job state, and frontend serving
pipeline/    Vault reader, note scoring, and training-data generation
training/    MLX, Unsloth, export helpers, and Colab notebook
models/      Trained model artifacts and GGUF outputs
output/      Generated JSONL files, checkpoints, and session data
uploads/     Temporary uploaded vault contents
```

Key files:

- [server/app.py](/Users/csuftitan/Desktop/ownLLM/server/app.py)
- [server/routes/training.py](/Users/csuftitan/Desktop/ownLLM/server/routes/training.py)
- [server/routes/jobs.py](/Users/csuftitan/Desktop/ownLLM/server/routes/jobs.py)
- [pipeline/vault_reader.py](/Users/csuftitan/Desktop/ownLLM/pipeline/vault_reader.py)
- [pipeline/data_generator.py](/Users/csuftitan/Desktop/ownLLM/pipeline/data_generator.py)
- [training/train_mlx.py](/Users/csuftitan/Desktop/ownLLM/training/train_mlx.py)
- [training/train_unsloth.py](/Users/csuftitan/Desktop/ownLLM/training/train_unsloth.py)

## Troubleshooting

### Ollama Is Not Running

If chat or model discovery fails, start Ollama locally:

```bash
ollama serve
```

### A Hugging Face Model Will Not Download

Check:

- whether the model is gated
- whether you accepted the model license on Hugging Face
- whether `HF_TOKEN` is set in `.env`

### Local Training Is Too Slow Or Runs Out Of Memory

Use the Colab flow. The UI already recommends it on weak hardware, and the notebook is part of the repo.

### The Frontend Loads But The Root Path Does Not Work In Production

Build the frontend first:

```bash
cd frontend
npm run build
```

The FastAPI app only serves the SPA from `frontend/dist` when that build output exists.

## Privacy

The app runs locally, but note content sent to generate training pairs follows the policy of the LLM provider you choose for generation. Fine-tuning, model files, and local chat stay on your machine unless you deliberately use a hosted environment such as Colab.
