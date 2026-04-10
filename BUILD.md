# Personal Knowledge Base Fine-Tuner — Build Context

## What This Is

A Python pipeline that takes an Obsidian vault (or any folder of `.md` files) and
produces a `.jsonl` training dataset ready for QLoRA fine-tuning. This document is
the full context needed to build **Step 1** (vault reader + note scorer) and
**Step 2** (training data generator).

---

## Project Structure

```
md2LLM/
├── src/
│   ├── vault_reader.py       ← Step 1: read + score notes
│   ├── data_generator.py     ← Step 2: generate JSONL training data
│   └── utils.py              ← shared helpers
├── output/
│   └── training_data.jsonl   ← final output
├── config.yaml               ← user config
├── requirements.txt
└── README.md
```

---

## Step 1 — Vault Reader (`vault_reader.py`)

### What It Does
- Recursively walks the vault folder and finds all `.md` files
- Parses each note: extracts frontmatter (YAML), body text, wikilinks, tags
- Scores each note on quality (0.0 – 1.0)
- Returns a filtered list of `Note` objects above a quality threshold

### Note Data Model

```python
@dataclass
class Note:
    path: str           # absolute file path
    title: str          # filename without .md extension
    body: str           # full markdown body text
    frontmatter: dict   # parsed YAML frontmatter (tags, date, etc.)
    tags: list[str]     # combined from frontmatter + inline #tags
    wikilinks: list[str]# [[linked notes]] extracted from body
    word_count: int     # number of words in body
    quality_score: float# 0.0–1.0, see scoring rules below
```

### Quality Scoring Rules

Score each note from 0.0 to 1.0. Rules:

| Condition | Score Effect |
|---|---|
| word_count < 50 | Skip entirely (score = 0) |
| word_count 50–150 | score = 0.3 |
| word_count 150–300 | score = 0.6 |
| word_count > 300 | score = 0.8 base |
| Has frontmatter | +0.1 |
| Has wikilinks (backlinks) | +0.1 |
| Has tags | +0.05 |
| Title contains "untitled" | -0.3 |
| Body is mostly bullet points only (>80% lines start with `-`) | -0.2 |
| Frontmatter has `status: draft` or `#draft` tag | Score = 0 (skip) |
| Frontmatter has `status: raw` or `#raw` tag | Score = 0 (skip) |

Cap score at 1.0. Only return notes with score >= 0.4 (configurable threshold).

### Parsing Details

**Frontmatter**: YAML block between `---` delimiters at top of file.
```
---
tags: [python, learning]
date: 2024-01-15
status: published
---
```

**Wikilinks**: Extract all `[[...]]` patterns from body.
- `[[Note Title]]` → "Note Title"
- `[[Note Title|Alias]]` → "Note Title" (ignore alias)

**Inline tags**: Extract all `#word` patterns from body text.
- Ignore `#` inside code blocks (between ``` markers)
- Only extract tags that are standalone words (not part of a heading like `## heading`)

**Clean body text** before scoring:
- Strip frontmatter block
- Strip Obsidian comments `%%...%%`
- Keep headings, paragraphs, lists — that is the content

### Function Signatures

```python
def read_vault(vault_path: str, min_quality: float = 0.4) -> list[Note]:
    """
    Walk vault_path recursively, parse all .md files,
    score them, return notes above min_quality threshold.
    Skips: .obsidian/ folder, template files, files in _templates/ folder.
    """

def parse_note(file_path: str) -> Note:
    """Parse a single .md file into a Note object."""

def score_note(note: Note) -> float:
    """Score a note 0.0–1.0 based on quality rules above."""

def extract_frontmatter(content: str) -> tuple[dict, str]:
    """
    Split raw file content into (frontmatter_dict, body_text).
    Returns ({}, full_content) if no frontmatter found.
    """

def extract_wikilinks(body: str) -> list[str]:
    """Extract all [[wikilink]] targets from body text."""

def extract_tags(body: str, frontmatter: dict) -> list[str]:
    """Extract tags from both frontmatter and inline #tags in body."""
```

### Stats Output

After reading the vault, print a summary:
```
Vault summary:
  Total .md files found:  247
  Skipped (too short):     43
  Skipped (draft/raw):     18
  Skipped (low quality):   31
  Passed quality filter:  155
  Average quality score:  0.71
```

---

## Step 2 — Training Data Generator (`data_generator.py`)

### What It Does
- Takes the list of `Note` objects from Step 1
- For each note, calls an LLM to generate training pairs
- Supports 4 training formats based on user's chosen goal
- Deduplicates and validates pairs
- Writes final `.jsonl` file

### The 4 Training Goals

User picks ONE goal when running the pipeline. This controls which format is used.

#### Goal 1: `knowledge`
User wants to ask questions about what they know.

Output format (Alpaca-style):
```json
{"instruction": "What is spaced repetition?", "input": "", "output": "Spaced repetition is a learning technique where you review information at increasing intervals. The core idea is that you should review something just before you would forget it..."}
```

LLM prompt to generate these:
```
Given this note, generate {n} question-answer pairs a user might ask about this content.
The questions should be natural, conversational questions.
The answers should be comprehensive and written in first person as if the note author is explaining.
Return ONLY a JSON array of objects with "instruction" and "output" keys.

Note title: {title}
Note content:
{body}
```

#### Goal 2: `style`
User wants the model to write in their voice and style.

Output format:
```json
{"instruction": "Write a short explanation of why consistency matters in habit building", "input": "", "output": "[user's actual writing style reproduced from notes]"}
```

LLM prompt:
```
Analyze the writing style of this note (tone, sentence length, vocabulary, use of examples).
Then generate {n} writing prompts paired with responses that match this exact style.
The responses should sound like the same author wrote them.
Return ONLY a JSON array of objects with "instruction" and "output" keys.

Note title: {title}
Note content:
{body}
```

#### Goal 3: `reasoning`
User wants the model to connect ideas the way they do.

Output format:
```json
{"instruction": "How does stoicism connect to my productivity system?", "input": "", "output": "The connection I see between stoicism and productivity is..."}
```

LLM prompt:
```
This note contains ideas and concepts. Generate {n} reasoning questions that ask
about connections, implications, or applications of these ideas.
Answers should reflect the author's thinking style and connect to related concepts mentioned.
Return ONLY a JSON array of objects with "instruction" and "output" keys.

Note title: {title}
Note content:
{body}
Linked notes (context): {wikilinks}
```

#### Goal 4: `chatbot`
User wants a conversational AI version of themselves.

Output format (ChatML):
```json
{"messages": [{"role": "user", "content": "What do you think about deep work?"}, {"role": "assistant", "content": "From what I've studied and experienced, deep work is..."}]}
```

LLM prompt:
```
This is a personal note. Generate {n} natural conversations where someone asks the
note author about topics from this note. The author responds in first person,
drawing on the note content but speaking naturally as in a conversation.
Return ONLY a JSON array of objects with "messages" key containing a list of role/content pairs.

Note title: {title}
Note content:
{body}
```

### Pairs Per Note

Scale based on note quality score and word count:

| Quality Score | Word Count | Pairs Generated |
|---|---|---|
| 0.4 – 0.6 | any | 2 pairs |
| 0.6 – 0.8 | < 300 words | 3 pairs |
| 0.6 – 0.8 | > 300 words | 5 pairs |
| 0.8 – 1.0 | < 300 words | 5 pairs |
| 0.8 – 1.0 | > 300 words | 8 pairs |

### LLM Configuration

Use `litellm` so the user can plug in any LLM provider:

```python
import litellm

response = litellm.completion(
    model=config["model"],          # e.g. "gpt-4o-mini", "ollama/llama3.2", "claude-haiku-4-5-20251001"
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7,
    response_format={"type": "json_object"}  # force JSON output
)
```

Default model in config: `ollama/llama3.2` (fully local, no API key needed).
Cheap cloud alternative: `gpt-4o-mini` (~$0.002 per note).

### Validation Rules

Before writing a pair to JSONL, validate:
- `instruction` length > 10 characters
- `output` length > 30 characters  
- `output` is NOT a refusal ("I cannot", "I don't have", "As an AI")
- No duplicate instructions (use set to track seen instructions)
- For chatbot format: messages list has at least 2 entries

### Function Signatures

```python
def generate_training_data(
    notes: list[Note],
    goal: str,                    # "knowledge" | "style" | "reasoning" | "chatbot"
    model: str,
    output_path: str
) -> dict:
    """
    Main function. Iterates notes, generates pairs, writes JSONL.
    Returns stats dict: {total_notes, total_pairs, skipped, output_path}
    """

def generate_pairs_for_note(
    note: Note,
    goal: str,
    model: str,
    n_pairs: int
) -> list[dict]:
    """
    Call LLM to generate n_pairs training pairs for one note.
    Returns list of dicts in the correct format for the goal.
    """

def build_prompt(note: Note, goal: str, n_pairs: int) -> str:
    """Build the LLM prompt for the given goal."""

def validate_pair(pair: dict, goal: str) -> bool:
    """Validate a single training pair. Returns True if valid."""

def write_jsonl(pairs: list[dict], output_path: str) -> None:
    """Write list of dicts to a .jsonl file, one JSON object per line."""
```

### Progress Display

Show progress as notes are processed:
```
Generating training data...
Goal: knowledge | Model: ollama/llama3.2

[████████████░░░░░░░░] 62/155 notes | 341 pairs generated | ETA: 4m 12s

Current: "Spaced Repetition Systems.md" (quality: 0.84, generating 8 pairs)
```

Use `tqdm` for the progress bar.

### Final Stats Output

```
Training data generation complete!
─────────────────────────────────
  Notes processed:     155
  Notes failed:          3
  Total pairs:         712
  Valid pairs:         698
  Duplicates removed:   14
  Output file:         output/training_data.jsonl
  File size:           1.2 MB
─────────────────────────────────
Next step: python train.py --data output/training_data.jsonl
```

---

## Config File (`config.yaml`)

```yaml
vault:
  path: "~/my-vault"          # path to Obsidian vault or markdown folder
  min_quality: 0.4            # minimum quality score to include a note
  exclude_folders:            # folders to skip
    - .obsidian
    - _templates
    - templates
    - attachments

training:
  goal: "knowledge"           # knowledge | style | reasoning | chatbot
  model: "ollama/llama3.2"    # any litellm-compatible model string
  output_path: "output/training_data.jsonl"
  max_notes: null             # null = process all, or set a number for testing
```

---

## Requirements (`requirements.txt`)

```
pyyaml>=6.0
litellm>=1.0
tqdm>=4.65
python-frontmatter>=1.0
regex>=2023.0
dataclasses; python_version < "3.7"
```

---

## Entry Point (`main.py`)

```python
# Usage:
# python -m pipeline.main --vault ./my-vault --goal knowledge
# python -m pipeline.main --vault ./my-vault --goal style --model gpt-4o-mini
# python -m pipeline.main --config config.yaml

import argparse
from src.vault_reader import read_vault
from src.data_generator import generate_training_data
import yaml

def main():
    parser = argparse.ArgumentParser(description="Generate fine-tuning data from your Obsidian vault")
    parser.add_argument("--vault", help="Path to vault folder")
    parser.add_argument("--goal", choices=["knowledge", "style", "reasoning", "chatbot"], default="knowledge")
    parser.add_argument("--model", default="ollama/llama3.2")
    parser.add_argument("--config", help="Path to config.yaml")
    parser.add_argument("--min-quality", type=float, default=0.4)
    parser.add_argument("--output", default="output/training_data.jsonl")
    args = parser.parse_args()

    # Step 1: Read vault
    print(f"\nReading vault: {args.vault}")
    notes = read_vault(args.vault, min_quality=args.min_quality)

    # Step 2: Generate training data
    stats = generate_training_data(
        notes=notes,
        goal=args.goal,
        model=args.model,
        output_path=args.output
    )

    print(f"\nDone! {stats['total_pairs']} training pairs saved to {args.output}")

if __name__ == "__main__":
    main()
```

---

## Key Implementation Notes

1. **Always strip the `.obsidian/` folder** — it contains settings JSON, not notes.
2. **Handle encoding errors** — some vaults have non-UTF-8 files. Use `errors="ignore"` when reading.
3. **LLM JSON parsing** — wrap all LLM responses in try/except. If JSON parse fails, skip that note and log a warning. Do not crash.
4. **Rate limiting** — add a small delay between LLM calls (0.5s default) to avoid hitting API rate limits. Make this configurable.
5. **Resumability** — keep a `processed_notes.txt` file in output/ with already-processed note paths. If the run is interrupted, skip already-processed notes on restart.
6. **The output JSONL must have one valid JSON object per line** — no trailing commas, no arrays wrapping the whole file. Each line is standalone.
7. **For Ollama** — check if Ollama is running before starting (`curl http://localhost:11434` check). If not running, print a helpful message.

---

## What Good Output Looks Like

A correctly generated `training_data.jsonl` for the `knowledge` goal:
```jsonl
{"instruction": "What is the Feynman Technique?", "input": "", "output": "The Feynman Technique is a learning method I use where you explain a concept as if teaching it to a child. If you can't explain it simply, you don't understand it well enough yet. The process has four steps: choose a concept, explain it simply, identify gaps when you get stuck, and go back to the source material to fill those gaps."}
{"instruction": "How do I apply spaced repetition to programming concepts?", "input": "", "output": "For programming, I use spaced repetition by creating cards for syntax patterns, algorithm approaches, and common bugs I've hit. The key insight I found is that you should create cards after solving a problem, not before — that way the card captures something you actually struggled with."}
{"instruction": "What's the difference between active and passive recall?", "input": "", "output": "Active recall means forcing your brain to retrieve information without looking at it — flashcards, practice problems, writing from memory. Passive recall is re-reading or re-watching. My notes show that active recall is significantly more effective for retention even though it feels harder."}
```

---

## Testing

To test without a real vault, create a small test vault:

```bash
mkdir test-vault
cat > test-vault/learning.md << 'EOF'
---
tags: [learning, productivity]
date: 2024-01-15
---
# Learning Techniques

Spaced repetition is one of the most effective learning techniques I have found.
The core idea is that you review material at increasing intervals based on how well
you remember it. Tools like Anki implement this with an algorithm.

The Feynman Technique pairs well with spaced repetition. You explain a concept simply
to identify gaps, then use spaced repetition to solidify the understanding over time.

Active recall is more effective than passive re-reading. Instead of reading notes again,
close them and try to write down everything you remember. This feels harder but produces
much stronger retention. See also [[Memory Systems]] and [[Productivity]].
EOF

python -m pipeline.main --vault ./test-vault --goal knowledge --model ollama/llama3.2
```

Expected: 3-5 high quality Q&A pairs generated from this one note.
