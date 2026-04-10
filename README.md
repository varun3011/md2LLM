# md2LLM

**Turn markdown notes into a small local model you can chat with.**

md2LLM reads your personal markdown notes, generates training pairs, fine-tunes
a compact base model, and runs the result locally through a browser workflow.
Your notes stay on your machine except for the optional API call used to create
training data.

## How It Works

```text
Your notes -> Training data -> Fine-tuned model -> Chat
```

1. Point md2LLM at an Obsidian vault or any folder of markdown files
2. Review the notes selected for training data generation
3. Generate Q&A, style, reasoning, or chatbot training pairs
4. Select a base model; md2LLM maps it to a Hugging Face repo for training
5. Fine-tune locally on MLX or Unsloth, or use the Google Colab fallback
6. Export a model artifact and chat with it through the local app

## Setup

### Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher
- Ollama installed and running (ollama.com)
- OpenAI API key (for training data generation)
- 16GB+ RAM or an NVIDIA GPU recommended for local training

### Install

```bash
# Clone the repo
git clone https://github.com/yourusername/md2LLM
cd md2LLM

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### Configure

```bash
# Copy the environment template
cp .env.example .env

# Open .env and add your OpenAI API key
# OPENAI_API_KEY=your-openai-api-key-here
```

### Run

```bash
# Start the backend server
uvicorn server.app:app --host 127.0.0.1 --port 8000

# In a separate terminal, start the frontend (development)
cd frontend && npm run dev

# Open your browser
# http://localhost:5173
```

## Usage

1. Upload your Obsidian vault or point to a markdown folder
2. Pick your goal - Knowledge, Style, Reasoning, or Chatbot
3. Generate training data from your notes
4. Select a base model, then confirm the Hugging Face repo used for training
5. Configure training settings
6. Start training - takes 15-40 minutes depending on hardware
7. Chat with your personalized model

## Hardware Requirements

| Hardware | Training Time | Notes |
|---|---|---|
| Mac Apple Silicon 16GB+ | 15-25 min | Uses MLX - recommended |
| Mac Apple Silicon 8GB | Varies | Colab recommended; local training may freeze |
| NVIDIA GPU 8GB+ | 10-20 min | Uses Unsloth |
| NVIDIA GPU 4-6GB | 20-35 min | Use smaller model |
| CPU only or low RAM | 15-25 min | Uses Google Colab fallback |
| Google Colab | 15-25 min | Free T4 GPU |

## Supported Base Models

Training uses Hugging Face model repositories. Before training starts, md2LLM
checks the local Hugging Face cache at `~/.cache/huggingface/hub` for the
selected repo. If the model is not cached, md2LLM downloads it from Hugging Face.
Ollama is only used later to run the exported model after training.

| UI model family | Training repo |
|---|---|
| Qwen 2.5 1.5B | `Qwen/Qwen2.5-1.5B-Instruct` |
| Llama 3.2 1B | `meta-llama/Llama-3.2-1B-Instruct` |
| Llama 3.2 3B | `meta-llama/Llama-3.2-3B-Instruct` |
| Phi-3 Mini | `microsoft/Phi-3-mini-4k-instruct` |

After training, md2LLM exports the result so it can be loaded and run locally.

```text
Select Hugging Face repo
        |
        v
Check ~/.cache/huggingface/hub
        |
        +--> cached: train immediately
        |
        +--> not cached: download from Hugging Face, then train
        |
        v
Export trained model
        |
        v
Load/run with Ollama
```

## Privacy

The app runs locally on your machine. Training data generation uses your
configured LLM provider, so note excerpts sent for pair generation follow that
provider's API policy. Local training, model export, and chat run through the
local backend and your local model files.

## Architecture

```text
frontend/ React + Vite app
        |
        v
server/ FastAPI routes
        |
        +--> pipeline/ markdown reader and training data generator
        |
        +--> training/ MLX, Unsloth, export, and Colab notebook
        |
        +--> models/ trained model artifacts
        |
        +--> output/ generated JSONL training data
```

### Frontend

`frontend/` contains the React workflow:

- `SelectVault` loads markdown files and starts a generation job
- `ReviewFiles` lets the user inspect candidate notes
- `Generate` streams training data generation progress
- `SelectModel` and `TrainConfig` choose a base model and training settings
- `TrainRun` checks hardware, runs local training, or shows Colab steps
- `Chat` opens the local chat experience after the model is available

The Vite dev server proxies API requests to the FastAPI backend.

### Backend

`server/app.py` creates the FastAPI app and mounts route modules:

- `server/routes/jobs.py` manages job state, generated files, and downloads
- `server/routes/training.py` detects hardware, recommends local vs. Colab training, and starts training jobs
- `server/routes/models.py` discovers Ollama and local model files
- `server/routes/chat.py` handles chat requests
- `server/routes/frontend.py` serves the built frontend in production

Runtime configuration and output paths live in `server/config.py`.

### Pipeline

`pipeline/vault_reader.py` parses markdown files, frontmatter, wikilinks, tags,
and note quality. `pipeline/data_generator.py` turns accepted notes into JSONL
training pairs using the selected goal mode. Generated data is written to
`output/`.

### Training

`training/` contains the fine-tuning entry points:

- `train_mlx.py` for Apple Silicon MLX training
- `train_unsloth.py` for NVIDIA GPU training with Unsloth
- `trainer.py` for shared dataset and progress helpers
- `export.py` and `Modelfile` for local model export and Ollama setup
- `md2LLM_colab.ipynb` for the Google Colab fallback path

The backend blocks local training on weak devices and routes the user to Colab
when CPU-only or low-memory hardware would be unsafe.

See `docs/architecture.md` for a deeper technical overview.

## License

MIT
