from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tqdm.asyncio import tqdm as async_tqdm

from pipeline.vault_reader import Note

load_dotenv()
logger = logging.getLogger(__name__)

MAX_CONCURRENT = 20
BATCH_SIZE = 50
RATE_LIMIT_DELAY = 0.1
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0
MAX_TOKENS = 2000
TEMPERATURE = 0.7


@dataclass
class Checkpoint:
    processed_hashes: set[str] = field(default_factory=set)
    total_pairs: int = 0
    failed_notes: list[str] = field(default_factory=list)


def get_note_hash(note: Note) -> str:
    """Stable hash for a note based on its path and content."""
    content = f"{note.path}:{note.body[:200]}"
    return hashlib.md5(content.encode()).hexdigest()


def load_checkpoint(checkpoint_path: str) -> Checkpoint:
    """
    Load checkpoint from disk.
    If checkpoint file does not exist, return empty Checkpoint.
    If file is corrupt, log warning and return empty Checkpoint.
    """
    path = Path(checkpoint_path)
    if not path.exists():
        return Checkpoint()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return Checkpoint(
            processed_hashes=set(data.get("processed_hashes", [])),
            total_pairs=data.get("total_pairs", 0),
            failed_notes=data.get("failed_notes", []),
        )
    except Exception as exc:
        logger.warning(f"Corrupt checkpoint, starting fresh: {exc}")
        return Checkpoint()


def save_checkpoint(checkpoint: Checkpoint, checkpoint_path: str) -> None:
    """
    Save checkpoint atomically using a temp file then rename.
    This prevents corrupt checkpoints if the process is killed mid-write.
    """
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    data = {
        "processed_hashes": list(checkpoint.processed_hashes),
        "total_pairs": checkpoint.total_pairs,
        "failed_notes": checkpoint.failed_notes,
    }
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle)
    tmp_path.replace(path)


def create_smart_batches(notes: list[Note], batch_size: int) -> list[list[Note]]:
    """
    Group notes into batches sorted by word count descending.
    This ensures long notes are processed first and batches are roughly
    similar in total token load.
    """
    sorted_notes = sorted(notes, key=lambda note: note.word_count, reverse=True)

    batches: list[list[Note]] = []
    current_batch: list[Note] = []
    current_word_count = 0
    word_budget = batch_size * 300

    for note in sorted_notes:
        if len(current_batch) >= batch_size or (
            current_word_count + note.word_count > word_budget and current_batch
        ):
            batches.append(current_batch)
            current_batch = [note]
            current_word_count = note.word_count
        else:
            current_batch.append(note)
            current_word_count += note.word_count

    if current_batch:
        batches.append(current_batch)

    return batches


async def call_llm_async(
    client: AsyncOpenAI,
    prompt: str,
    semaphore: asyncio.Semaphore,
    note_title: str,
    model: str,
) -> Optional[str]:
    """
    Make one async API call with retry and exponential backoff.
    Returns raw string response or None on failure.
    """
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                message = response.choices[0].message.content
                return message.strip() if message else None
            except Exception as exc:
                error_str = str(exc).lower()

                if "429" in error_str or "rate limit" in error_str:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"Rate limit hit for '{note_title}', waiting {delay}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    continue

                if "context" in error_str or "token" in error_str:
                    logger.warning(f"Note '{note_title}' too long for context window, skipping")
                    return None

                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning(f"API error for '{note_title}': {exc}, retrying in {delay}s")
                await asyncio.sleep(delay)

        logger.error(f"All {MAX_RETRIES} attempts failed for '{note_title}'")
        return None


def parse_llm_response(raw: Optional[str], goal: str, note_title: str) -> list[dict[str, Any]]:
    """
    Parse raw LLM string response into list of training pair dicts.
    Returns empty list on any parse failure rather than raising.
    """
    del goal

    if not raw:
        return []

    try:
        raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^```\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        raw = raw.strip()

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            logger.warning(f"No JSON array found in response for '{note_title}'")
            return []

        pairs = json.loads(match.group())
        if not isinstance(pairs, list):
            return []

        return pairs
    except json.JSONDecodeError as exc:
        logger.warning(f"JSON parse error for '{note_title}': {exc}")
        return []
    except Exception as exc:
        logger.warning(f"Parse error for '{note_title}': {exc}")
        return []


async def process_note_async(
    note: Note,
    goal: str,
    model: str,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    seen_instructions: set[str],
    seen_lock: asyncio.Lock,
    all_notes_by_title: dict[str, Note],
    use_llm_validation: bool,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Process one note asynchronously.
    Returns (note_hash, list_of_valid_pairs).
    """
    note_hash = get_note_hash(note)
    n_pairs = calculate_n_pairs(note)
    link_context = enrich_note_with_links(note, all_notes_by_title) if all_notes_by_title else ""
    prompt = build_prompt(note, goal, n_pairs, link_context)

    raw = await call_llm_async(client, prompt, semaphore, note.title, model)
    if raw is None:
        raise RuntimeError(f"LLM call failed for '{note.title}'")
    pairs = parse_llm_response(raw, goal, note.title)

    valid_pairs: list[dict[str, Any]] = []
    async with seen_lock:
        for pair in pairs:
            if validate_pair(pair, goal, seen_instructions):
                valid_pairs.append(pair)

    if use_llm_validation and valid_pairs:
        filtered_pairs: list[dict[str, Any]] = []
        for pair in valid_pairs:
            is_valid = await asyncio.to_thread(validate_pair_with_llm, pair, note, model)
            if is_valid:
                filtered_pairs.append(pair)
        valid_pairs = filtered_pairs

    return note_hash, valid_pairs


async def _delayed_process_note(
    note: Note,
    goal: str,
    model: str,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    seen_instructions: set[str],
    seen_lock: asyncio.Lock,
    all_notes_by_title: dict[str, Note],
    use_llm_validation: bool,
    delay_seconds: float,
) -> tuple[str, list[dict[str, Any]]]:
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    return await process_note_async(
        note=note,
        goal=goal,
        model=model,
        client=client,
        semaphore=semaphore,
        seen_instructions=seen_instructions,
        seen_lock=seen_lock,
        all_notes_by_title=all_notes_by_title,
        use_llm_validation=use_llm_validation,
    )


async def process_batch_async(
    batch: list[Note],
    goal: str,
    model: str,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    checkpoint: Checkpoint,
    checkpoint_path: str,
    output_path: str,
    seen_instructions: set[str],
    seen_lock: asyncio.Lock,
    progress_bar: Any,
    all_notes: list[Note],
    all_notes_by_title: dict[str, Note],
    use_llm_validation: bool,
    progress_callback: Any = None,
) -> list[dict[str, Any]]:
    """
    Process one batch of notes concurrently, append results, then checkpoint.
    """
    pending = [note for note in batch if get_note_hash(note) not in checkpoint.processed_hashes]

    if not pending:
        progress_bar.update(len(batch))
        return []

    tasks = [
        _delayed_process_note(
            note=note,
            goal=goal,
            model=model,
            client=client,
            semaphore=semaphore,
            seen_instructions=seen_instructions,
            seen_lock=seen_lock,
            all_notes_by_title=all_notes_by_title,
            use_llm_validation=use_llm_validation,
            delay_seconds=index * RATE_LIMIT_DELAY,
        )
        for index, note in enumerate(pending)
    ]

    batch_pairs: list[dict[str, Any]] = []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    completed_count = len(checkpoint.processed_hashes)

    for note, result in zip(pending, results):
        if isinstance(result, Exception):
            logger.error(f"Unexpected error for '{note.title}': {result}")
            if note.path not in checkpoint.failed_notes:
                checkpoint.failed_notes.append(note.path)
        else:
            note_hash, pairs = result
            batch_pairs.extend(pairs)
            checkpoint.processed_hashes.add(note_hash)
            checkpoint.total_pairs += len(pairs)
            if note.path in checkpoint.failed_notes:
                checkpoint.failed_notes.remove(note.path)

        progress_bar.update(1)
        completed_count += 1

        if progress_callback:
            progress_callback(
                completed=completed_count,
                total=len(all_notes),
                pairs_so_far=checkpoint.total_pairs,
                current_note=note.title,
            )

    if batch_pairs:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a", encoding="utf-8") as handle:
            for pair in batch_pairs:
                handle.write(json.dumps(pair, ensure_ascii=False) + "\n")

    save_checkpoint(checkpoint, checkpoint_path)
    return batch_pairs


async def generate_training_data_async(
    notes: list[Note],
    goal: str,
    model: str = "gpt-4o-mini",
    output_path: str = "output/training_data.jsonl",
    checkpoint_path: str = "output/checkpoint.json",
    resume: bool = True,
    progress_callback=None,
    use_llm_validation: bool = False,
) -> dict[str, Any]:
    """
    Main async entry point for training data generation.
    """
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    checkpoint = load_checkpoint(checkpoint_path) if resume else Checkpoint()

    if not resume:
        Path(output_path).unlink(missing_ok=True)
        Path(checkpoint_path).unlink(missing_ok=True)
        checkpoint = Checkpoint()

    _seed_seen_from_output(output_path, checkpoint.processed_hashes, notes)

    already_done = len(checkpoint.processed_hashes)
    remaining = [note for note in notes if get_note_hash(note) not in checkpoint.processed_hashes]
    all_notes_by_title = {note.title.lower(): note for note in notes}

    if already_done > 0 and resume:
        print(
            f"\nResuming from checkpoint: {already_done} notes already processed, "
            f"{len(remaining)} remaining"
        )

    batches = create_smart_batches(remaining, BATCH_SIZE)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    seen_instructions = _load_seen_instructions(output_path) if resume else set()
    seen_lock = asyncio.Lock()

    print("\nmd2LLM — Generating training data")
    print("─────────────────────────────────────")
    print(f"  Notes to process:  {len(remaining)}")
    print(f"  Already done:      {already_done}")
    print(f"  Batches:           {len(batches)}")
    print(f"  Concurrency:       {MAX_CONCURRENT} parallel calls")
    print(f"  Goal:              {goal}")
    print(f"  Model:             {model}")
    print(f"  LLM validation:    {'on' if use_llm_validation else 'off'}")
    print("─────────────────────────────────────\n")

    start_time = time.time()

    with async_tqdm(total=len(remaining), desc="Processing notes", unit="note") as pbar:
        for batch in batches:
            await process_batch_async(
                batch=batch,
                goal=goal,
                model=model,
                client=client,
                semaphore=semaphore,
                checkpoint=checkpoint,
                checkpoint_path=checkpoint_path,
                output_path=output_path,
                seen_instructions=seen_instructions,
                seen_lock=seen_lock,
                progress_bar=pbar,
                all_notes=notes,
                all_notes_by_title=all_notes_by_title,
                use_llm_validation=use_llm_validation,
                progress_callback=progress_callback,
            )

    elapsed = time.time() - start_time
    output_file = Path(output_path)
    line_count = 0
    if output_file.exists():
        with output_file.open("r", encoding="utf-8") as handle:
            line_count = sum(1 for _ in handle)

    stats = {
        "total_notes": len(notes),
        "notes_processed": len(remaining),
        "notes_skipped_checkpoint": already_done,
        "notes_failed": len(checkpoint.failed_notes),
        "total_pairs": line_count,
        "elapsed_seconds": round(elapsed, 1),
        "output_path": output_path,
    }

    print(f"\n{'─' * 45}")
    print(f"  Notes processed:    {stats['notes_processed']}")
    print(f"  Notes failed:       {stats['notes_failed']}")
    print(f"  Total pairs:        {stats['total_pairs']}")
    print(f"  Time elapsed:       {elapsed:.0f}s")
    print(f"  Output:             {output_path}")
    print(f"{'─' * 45}")

    if checkpoint.failed_notes:
        print("\n  Failed notes saved to checkpoint.")
        print("  Re-run without --no-resume to continue from the checkpoint.")

    print(f"\n  Next step: python train.py --data {output_path}\n")

    if output_file.exists():
        print("Sample output:")
        print("─" * 45)
        with output_file.open("r", encoding="utf-8") as handle:
            for i, line in enumerate(handle):
                if i >= 2:
                    break
                pair = json.loads(line)
                question = pair.get("instruction", "")
                answer = pair.get("output", "")
                print(f"Q: {question}")
                print(f"A: {answer[:200]}{'...' if len(answer) > 200 else ''}")
                print()

    return stats


def generate_training_data(
    notes: list[Note],
    goal: str,
    model: str = "gpt-4o-mini",
    output_path: str = "output/training_data.jsonl",
    checkpoint_path: str = "output/checkpoint.json",
    resume: bool = True,
    use_llm_validation: bool = False,
) -> dict[str, Any]:
    """
    Sync wrapper around the async implementation.
    This is the public API called from main.py.
    """
    return asyncio.run(
        generate_training_data_async(
            notes=notes,
            goal=goal,
            model=model,
            output_path=output_path,
            checkpoint_path=checkpoint_path,
            resume=resume,
            use_llm_validation=use_llm_validation,
        )
    )


def build_prompt(note: "Note", goal: str, n_pairs: int, link_context: str = "") -> str:
    link_section = f"\nCONTEXT FROM LINKED NOTES:\n{link_context}\n" if link_context else ""

    if goal == "knowledge":
        return f"""You are creating fine-tuning training data for a personal knowledge model.

The user is a researcher/student who has taken detailed notes on topics they study deeply.
Your job is to generate {n_pairs} high-quality question-answer training pairs from their note.
These pairs will be used to fine-tune a small language model so it can answer questions
the way the note author would — with depth, nuance, and personal insight.

NOTE TITLE: {note.title}

NOTE CONTENT:
{note.body[:4000]}{link_section}

LINKED CONCEPTS: {', '.join(note.wikilinks) if note.wikilinks else 'none'}

TAGS: {', '.join(note.tags) if note.tags else 'none'}

---

Generate {n_pairs} training pairs following ALL of these rules:

QUESTION RULES:
1. Questions must be specific to this note's actual content — never generic
2. Questions should sound like what a curious person would naturally ask
3. Generate different TYPES of questions across the pairs:
   - "How do you..." (application)
   - "Why does..." (reasoning)
   - "What is the difference between..." (comparison, if note has multiple concepts)
   - "When should you..." (decision making)
   - "What happens when..." (consequence)
   - "How does X connect to Y..." (connection, use wikilinks as hints)
4. Never generate: "What is the main idea", "Summarize this note", "What does this note say"

ANSWER RULES:
1. Minimum 4 sentences, no maximum
2. Written in first person as the note author speaking — "From what I have studied...", "The way I understand it...", "In my experience...", "What I have found is..."
3. Must synthesize the note content — explain it, do not copy paste sentences
4. Show reasoning and insight, not just facts
5. Reference linked concepts naturally when relevant
6. End with a complete sentence — never truncate
7. If the note mentions a personal experience or opinion, reflect that voice

STRICT OUTPUT FORMAT:
Return ONLY a valid JSON array. No explanation before or after. No markdown fences.
[
  {{
    "instruction": "specific natural question about the note content",
    "input": "",
    "output": "comprehensive first-person answer that synthesizes the note, minimum 4 sentences, ends with a complete sentence"
  }}
]"""

    if goal == "style":
        return f"""You are generating fine-tuning training data to teach a model to write in the same style as the note author.

Analyze the writing style of this note: the tone, sentence length, vocabulary choices, use of examples, and how ideas are structured.

Generate {n_pairs} writing prompt and response pairs where:
- The prompt asks the author to write or explain something related to the note topics
- The response is written in the exact same style as the note — same tone, same sentence rhythm, same vocabulary level
- Responses must be at least 4 sentences long
- Do not copy sentences directly from the note — write new content in the same style

Note title: {note.title}

Note content:
{note.body[:3000]}{link_section}

Return ONLY a valid JSON array. No explanation, no markdown, no extra text:
[
  {{"instruction": "write or explain something related to this topic", "input": "", "output": "response written in the author's exact style"}},
  {{"instruction": "another writing prompt", "input": "", "output": "another response in the author's style"}}
]"""

    if goal == "reasoning":
        return f"""You are generating fine-tuning training data that teaches a model to reason and connect ideas the way the note author does.

Generate {n_pairs} reasoning question and answer pairs where:
- Questions ask about connections between ideas, implications, or how concepts apply to real situations
- Questions reference the specific concepts and linked ideas in the note
- Answers show the author's reasoning process, connecting multiple ideas together
- Answers are 4-7 sentences, showing how the author thinks through a problem
- Use the wikilinks as hints for related concepts to reference in answers

Note title: {note.title}
Linked concepts: {', '.join(note.wikilinks) if note.wikilinks else 'none'}

Note content:
{note.body[:3000]}{link_section}

Return ONLY a valid JSON array. No explanation, no markdown, no extra text:
[
  {{"instruction": "reasoning question about connections or implications", "input": "", "output": "answer showing the reasoning process across multiple ideas"}},
  {{"instruction": "another reasoning question", "input": "", "output": "another reasoned answer"}}
]"""

    if goal == "chatbot":
        return f"""You are generating fine-tuning training data to create a conversational AI that talks like the note author.

Generate {n_pairs} natural conversations where:
- Someone asks the author about topics from this note in a casual, conversational way
- The author responds naturally in first person, as if in a real conversation
- Responses are conversational but substantive — 3-5 sentences
- The author shares their personal perspective and experience, not just facts
- Tone should match the note's tone exactly

Note title: {note.title}

Note content:
{note.body[:3000]}{link_section}

Return ONLY a valid JSON array. No explanation, no markdown, no extra text:
[
  {{"messages": [{{"role": "user", "content": "casual conversational question"}}, {{"role": "assistant", "content": "natural first-person conversational response"}}]}},
  {{"messages": [{{"role": "user", "content": "another question"}}, {{"role": "assistant", "content": "another natural response"}}]}}
]"""

    raise ValueError(f"Unsupported goal: {goal}")


def validate_pair(pair: dict, goal: str, seen_instructions: set[str]) -> bool:
    try:
        if goal == "chatbot":
            messages = pair.get("messages", [])
            if len(messages) < 2:
                return False
            user_msg = messages[0].get("content", "")
            assistant_msg = messages[1].get("content", "")
            if len(user_msg) < 10 or len(assistant_msg) < 50:
                return False
            if assistant_msg in seen_instructions:
                return False
            seen_instructions.add(assistant_msg)
            return True
        else:
            instruction = pair.get("instruction", "").strip()
            output = pair.get("output", "").strip()

            if len(instruction) < 10:
                return False
            if len(output) < 80:
                return False

            refusal_phrases = ["i cannot", "i don't have", "as an ai", "i am unable", "i'm not able"]
            if any(phrase in output.lower() for phrase in refusal_phrases):
                return False

            generic_phrases = ["what is the main idea", "what is the main point", "summarize this note", "what does this note say"]
            if any(phrase in instruction.lower() for phrase in generic_phrases):
                return False

            if instruction in seen_instructions:
                return False
            seen_instructions.add(instruction)

            if output and output[-1] not in [".", "!", "?", '"', "'"]:
                return False

            pair.setdefault("input", "")
            return True
    except Exception:
        return False


def validate_pair_with_llm(pair: dict, note: "Note", model: str) -> bool:
    """
    Use a cheap LLM call to score the pair quality.
    Returns True if the pair passes quality check, False to discard it.
    Only runs on pairs that passed basic validation.
    """
    import litellm, json, re

    prompt = f"""Rate this training data pair on a scale of 1-5 for quality.

Note it was generated from:
Title: {note.title}
Content preview: {note.body[:500]}

Training pair:
Question: {pair.get('instruction', '')}
Answer: {pair.get('output', '')}

Score criteria:
5 = Specific question, comprehensive answer (4+ sentences), first person voice, synthesizes content, shows insight
4 = Good question, solid answer (3+ sentences), mostly first person
3 = Acceptable but answer is shallow or question is slightly generic
2 = Generic question OR answer copies note text directly OR answer is too short
1 = Useless — generic question AND shallow answer, or truncated answer

Return ONLY a JSON object like this:
{{"score": 4, "reason": "one sentence reason"}}"""

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw)
        score = result.get("score", 0)
        if score < 4:
            print(f"    ✗ Pair discarded (score {score}): {result.get('reason', '')}")
            return False
        return True
    except Exception:
        return True


def enrich_note_with_links(note: "Note", notes_by_title: dict[str, Note]) -> str:
    """
    Find notes that are linked from this note via wikilinks.
    Return a short context string summarizing what linked notes are about.
    Only follows the first 2 wikilinks and adds the first 300 chars from each
    linked note body — just enough for context.
    """
    if not note.wikilinks:
        return ""

    context_parts: list[str] = []

    for link in note.wikilinks[:2]:
        linked = notes_by_title.get(link.lower())
        if linked and linked.body:
            preview = linked.body[:300].replace("\n", " ").strip()
            context_parts.append(f"[[{link}]]: {preview}")
        else:
            context_parts.append(f"[[{link}]]: (not yet in vault)")

    return "\n".join(context_parts) if context_parts else ""


def write_jsonl(pairs: list[dict[str, Any]], output_path: str) -> None:
    """Write list of dicts to a .jsonl file, one JSON object per line."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        for pair in pairs:
            handle.write(json.dumps(pair, ensure_ascii=False) + "\n")


def calculate_n_pairs(note: "Note") -> int:
    """
    Calculate how many training pairs to generate based on note richness.
    More content + more links = more pairs.
    """
    base = 2

    if note.word_count >= 500:
        base += 3
    elif note.word_count >= 300:
        base += 2
    elif note.word_count >= 150:
        base += 1

    if len(note.wikilinks) >= 5:
        base += 2
    elif len(note.wikilinks) >= 2:
        base += 1

    if note.quality_score >= 0.85:
        base += 1

    return min(base, 8)


def _load_seen_instructions(output_path: str) -> set[str]:
    seen: set[str] = set()
    path = Path(output_path)
    if not path.exists():
        return seen

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                pair = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "instruction" in pair:
                instruction = str(pair.get("instruction", "")).strip()
                if instruction:
                    seen.add(instruction)
            elif "messages" in pair:
                messages = pair.get("messages", [])
                if len(messages) >= 2:
                    assistant = str(messages[1].get("content", "")).strip()
                    if assistant:
                        seen.add(assistant)
    return seen


def _seed_seen_from_output(output_path: str, processed_hashes: set[str], notes: list[Note]) -> None:
    path = Path(output_path)
    if not path.exists():
        return
    if not processed_hashes:
        return

    known_hashes = {get_note_hash(note) for note in notes}
    processed_hashes.intersection_update(known_hashes)
