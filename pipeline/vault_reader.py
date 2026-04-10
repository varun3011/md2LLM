from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import frontmatter


@dataclass
class Note:
    path: str
    title: str
    body: str
    frontmatter: dict[str, Any]
    tags: list[str]
    wikilinks: list[str]
    word_count: int
    quality_score: float


EXCLUDED_FOLDERS = {".obsidian", "_templates", "templates", "attachments"}
INLINE_TAG_PATTERN = re.compile(r"(?<!#)(?<!\w)#([A-Za-z0-9][\w/-]*)")
WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\]]+)?\]\]")
OBSIDIAN_COMMENT_PATTERN = re.compile(r"%%.*?%%", re.DOTALL)
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.DOTALL)
WORD_PATTERN = re.compile(r"\b\w+\b")


def read_vault(vault_path: str, min_quality: float = 0.4) -> list[Note]:
    """
    Walk vault_path recursively, parse all .md files,
    score them, return notes above min_quality threshold.
    Skips: .obsidian/ folder, template files, files in _templates/ folder.
    """
    root = Path(vault_path).expanduser().resolve()
    notes: list[Note] = []
    total_files = 0
    quality_scores: list[float] = []
    skipped_too_short = 0
    skipped_draft_raw = 0
    skipped_low_quality = 0

    for file_path in root.rglob("*.md"):
        relative_parts = file_path.relative_to(root).parts
        if any(part in EXCLUDED_FOLDERS for part in relative_parts[:-1]):
            continue
        if file_path.stem.lower().startswith("template"):
            continue

        total_files += 1
        note = parse_note(str(file_path))
        score = score_note(note)
        note.quality_score = score
        quality_scores.append(score)

        status = str(note.frontmatter.get("status", "")).strip().lower()
        normalized_tags = {tag.lower() for tag in note.tags}
        if status in {"draft", "raw"} or {"draft", "raw"} & normalized_tags:
            skipped_draft_raw += 1
            continue
        if note.word_count < 50:
            skipped_too_short += 1
            continue
        if score < min_quality:
            skipped_low_quality += 1
            continue

        notes.append(note)

    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    print("Vault summary:")
    print(f"  Total .md files found: {total_files:4d}")
    print(f"  Skipped (too short):   {skipped_too_short:4d}")
    print(f"  Skipped (draft/raw):   {skipped_draft_raw:4d}")
    print(f"  Skipped (low quality): {skipped_low_quality:4d}")
    print(f"  Passed quality filter: {len(notes):4d}")
    print(f"  Average quality score: {avg_quality:.2f}")
    return notes


def parse_note(file_path: str) -> Note:
    """Parse a single .md file into a Note object."""
    path = Path(file_path).resolve()
    raw_content = path.read_text(encoding="utf-8", errors="ignore")
    post = frontmatter.loads(raw_content)

    body = _clean_body(raw_content)
    frontmatter_data = dict(post.metadata)
    title = path.stem
    wikilinks = extract_wikilinks(body)
    tags = extract_tags(body, frontmatter_data)
    word_count = len(WORD_PATTERN.findall(body))

    return Note(
        path=str(path),
        title=title,
        body=body,
        frontmatter=frontmatter_data,
        tags=tags,
        wikilinks=wikilinks,
        word_count=word_count,
        quality_score=0.0,
    )


def score_note(note: Note) -> float:
    """Score a note 0.0–1.0 based on quality rules above."""
    # Skip notes with explicit draft or raw tags
    skip_tags = {"draft", "raw", "inbox", "todo"}
    if any(tag.lower() in skip_tags for tag in note.tags):
        return 0.0

    if note.word_count < 50:
        return 0.0
    if note.word_count <= 150:
        score = 0.3
    elif note.word_count <= 300:
        score = 0.6
    else:
        score = 0.8

    if note.frontmatter:
        score += 0.1
    if note.wikilinks:
        score += 0.1
    if note.tags:
        score += 0.05
    if "untitled" in note.title.lower():
        score -= 0.3
    if _is_mostly_bullets(note.body):
        score -= 0.2

    return max(0.0, min(score, 1.0))


def extract_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Split raw file content into (frontmatter_dict, body_text).
    Returns ({}, full_content) if no frontmatter found.
    """
    post = frontmatter.loads(content)
    if post.metadata:
        return dict(post.metadata), post.content
    return {}, content


def extract_wikilinks(body: str) -> list[str]:
    """Extract all [[wikilink]] targets from body text."""
    return [match.strip() for match in WIKILINK_PATTERN.findall(body)]


def extract_tags(body: str, frontmatter: dict[str, Any]) -> list[str]:
    """Extract tags from both frontmatter and inline #tags in body."""
    tags: list[str] = []
    raw_frontmatter_tags = frontmatter.get("tags", [])

    if isinstance(raw_frontmatter_tags, str):
        raw_frontmatter_tags = [raw_frontmatter_tags]
    elif not isinstance(raw_frontmatter_tags, list):
        raw_frontmatter_tags = []

    for tag in raw_frontmatter_tags:
        cleaned = str(tag).strip().lstrip("#")
        if cleaned:
            tags.append(cleaned)

    for line in _strip_code_blocks(body).splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for match in INLINE_TAG_PATTERN.findall(line):
            cleaned = match.strip().lstrip("#")
            if cleaned:
                tags.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        lowered = tag.lower()
        if lowered not in seen:
            seen.add(lowered)
            deduped.append(tag)
    return deduped


def _clean_body(content: str) -> str:
    _, body = extract_frontmatter(content)
    body = FRONTMATTER_PATTERN.sub("", body, count=1)
    body = OBSIDIAN_COMMENT_PATTERN.sub("", body)
    return body.strip()


def _strip_code_blocks(body: str) -> str:
    lines: list[str] = []
    in_code_block = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            lines.append(line)
    return "\n".join(lines)


def _is_mostly_bullets(body: str) -> bool:
    content_lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not content_lines:
        return False
    bullet_lines = sum(1 for line in content_lines if line.startswith("-"))
    return (bullet_lines / len(content_lines)) > 0.8
