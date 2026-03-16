"""
Entity extraction from pull-request metadata for knowledge-graph ingestion.

Two layers:
    1. LLMEntityExtractor    — LLM-backed structured classification (primary)
    2. RegexEntityExtractor  — zero-cost file-extension + pattern fallback

Both satisfy the ``EntityExtractor`` protocol and return ``ExtractedEntities``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import vertexai
from vertexai.generative_models import GenerativeModel

from app.api.knowledge_graph.kg_taxonomy import (
    DOMAIN_PATTERNS,
    DOMAIN_SLUGS,
    EXTENSION_TO_LANGUAGE,
    FRAMEWORK_PATTERNS,
    FRAMEWORK_SLUGS,
    LANGUAGE_SLUGS,
    SKILL_PATTERNS,
    SKILL_SLUGS,
    TOOL_PATTERNS,
    TOOL_SLUGS,
    get_full_taxonomy_prompt,
)

# NOTE: DOMAIN_PATTERNS, SKILL_PATTERNS, FRAMEWORK_PATTERNS, TOOL_PATTERNS are
# kept imported for RegexEntityExtractor (the unavailability fallback).

logger = logging.getLogger(__name__)

# Languages that are too short or too ambiguous to detect reliably in plain text.
# They are still detected from file extensions during KG ingestion.
_TEXT_DETECT_SKIP: frozenset[str] = frozenset(
    {
        "C",
        "R",  # single letters — match almost every sentence
        "Go",  # extremely common English word
        "C++",
        "C#",
        "F#",  # special chars plus ambiguous base letter
    }
)

# Word-boundary patterns for unambiguous language names.
# NOTE: uses raw-string \b (word boundary), *not* \\w which would be a literal.
_LANGUAGE_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(language)}\b", re.IGNORECASE), language)
    for language in LANGUAGE_SLUGS
    if language not in _TEXT_DETECT_SKIP
]

# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ExtractedEntities:
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            [self.languages, self.frameworks, self.domains, self.skills, self.tools]
        )

    def merge(self, other: ExtractedEntities) -> ExtractedEntities:
        """Union both, deduplicate case-insensitively. First occurrence wins on case."""
        return ExtractedEntities(
            languages=_dedup(self.languages + other.languages),
            frameworks=_dedup(self.frameworks + other.frameworks),
            domains=_dedup(self.domains + other.domains),
            skills=_dedup(self.skills + other.skills),
            tools=_dedup(self.tools + other.tools),
        )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "languages": self.languages,
            "frameworks": self.frameworks,
            "domains": self.domains,
            "skills": self.skills,
            "tools": self.tools,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────


class EntityExtractor(Protocol):
    def extract(
        self,
        files: list[str],
        commit_messages: list[str],
        title: str,
        body: str,
        labels: list[str],
    ) -> ExtractedEntities: ...


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def _dedup(items: list[str]) -> list[str]:
    """Deduplicate preserving order, case-insensitive keying."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _to_lower_set(items: list[str]) -> set[str]:
    return {item.lower() for item in items}


def _merge_lists(primary: list[str], secondary: list[str]) -> list[str]:
    """Merge two lists preserving first-seen order, case-insensitive dedup."""
    return _dedup(primary + secondary)


def _as_list(value: Any) -> list[str]:
    """Safely coerce an LLM JSON field to ``list[str]``. Never raises."""
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return []


def _build_pr_context(
    files: list[str],
    commit_messages: list[str],
    title: str,
    body: str,
    labels: list[str],
) -> str:
    """Single combined text string fed to both extractors."""
    sections: list[str] = []
    if title:
        sections.append(f"PR Title: {title}")
    if labels:
        sections.append(f"Labels: {', '.join(labels)}")
    if body:
        sections.append(f"Description:\n{body[:1200]}")
    if files:
        sections.append("Changed files:\n" + "\n".join(files[:60]))
    if commit_messages:
        sections.append("Commits:\n" + "\n".join(commit_messages[:25]))
    return "\n\n".join(sections)


def _validate_against_taxonomy(entities: ExtractedEntities) -> ExtractedEntities:
    """
    Strip any values not present in the taxonomy.
    Protects the graph from dirty nodes caused by LLM hallucination or regex drift.
    Comparison is case-insensitive; original casing is preserved.
    """
    try:
        domain_set = {s.lower() for s in DOMAIN_SLUGS}
        skill_set = {s.lower() for s in SKILL_SLUGS}
        language_set = {s.lower() for s in LANGUAGE_SLUGS}
        framework_set = {s.lower() for s in FRAMEWORK_SLUGS}
        tool_set = {s.lower() for s in TOOL_SLUGS}

        return ExtractedEntities(
            languages=[
                language
                for language in entities.languages
                if language.lower() in language_set
            ],
            frameworks=[f for f in entities.frameworks if f.lower() in framework_set],
            domains=[d for d in entities.domains if d.lower() in domain_set],
            skills=[s for s in entities.skills if s.lower() in skill_set],
            tools=[t for t in entities.tools if t.lower() in tool_set],
        )
    except Exception:
        logger.warning("Unexpected error in _validate_against_taxonomy", exc_info=True)
        return entities


# ─────────────────────────────────────────────────────────────────────────────
# LLM system prompt  (built once, cached via prompt caching)
# ─────────────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = f"""You are a code intelligence system extracting metadata from pull requests.

{get_full_taxonomy_prompt()}

Output ONLY valid JSON — no markdown fences, no explanation, no extra keys:
{{
  "languages":  ["exact name from taxonomy"],
  "frameworks": ["exact name from taxonomy"],
  "domains":    ["exact slug from taxonomy"],
  "skills":     ["exact slug from taxonomy"],
  "tools":      ["exact name from taxonomy"]
}}

Rules:
- Every value MUST appear verbatim in the taxonomy
- Return [] if nothing clearly applies — never null
- languages:  infer from file extensions and explicit mentions
- frameworks: only if clearly signalled — import, config file, directory name
- domains:    what business/technical area does this PR touch?
- skills:     what specific capability does this PR demonstrate?
- tools:      specific platforms, databases, services mentioned or used
- Be conservative: 3 accurate entries beats 10 noisy ones
- Max 8 items per field
"""


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2: RegexEntityExtractor  (fallback + language layer)
# ─────────────────────────────────────────────────────────────────────────────


class RegexEntityExtractor:
    """Zero-cost extractor using file extensions and regex patterns."""

    def extract(
        self,
        files: list[str],
        commit_messages: list[str],
        title: str,
        body: str,
        labels: list[str],
    ) -> ExtractedEntities:
        combined_text = _build_pr_context(files, commit_messages, title, body, labels)
        file_languages = self._extract_languages(files)
        # Only supplement with text detection when no file list is available
        # (e.g. a plain-text task description in the scorer). During KG build
        # the file list is always populated and PR descriptions contain natural
        # English words that produce false positive language nodes (e.g. "C").
        text_languages = (
            self._extract_languages_from_text(combined_text) if not files else []
        )
        return ExtractedEntities(
            languages=_merge_lists(file_languages, text_languages),
            frameworks=self._run_patterns(FRAMEWORK_PATTERNS, combined_text),
            domains=self._run_patterns(DOMAIN_PATTERNS, combined_text),
            skills=self._run_patterns(SKILL_PATTERNS, combined_text),
            tools=self._run_patterns(TOOL_PATTERNS, combined_text),
        )

    def _extract_languages(self, files: list[str]) -> list[str]:
        """Detect languages from file extensions using EXTENSION_TO_LANGUAGE."""
        seen: set[str] = set()
        result: list[str] = []
        for file_path in files:
            # Extract extension (handle paths like "dir/file.py")
            dot_idx = file_path.rfind(".")
            if dot_idx == -1:
                continue
            ext = file_path[dot_idx:].lower()
            lang = EXTENSION_TO_LANGUAGE.get(ext)
            if lang and lang.lower() not in seen:
                seen.add(lang.lower())
                result.append(lang)
        return result

    def _extract_languages_from_text(self, text: str) -> list[str]:
        """Detect explicit language mentions in plain-English task or PR text."""
        seen: set[str] = set()
        result: list[str] = []
        for pattern, language in _LANGUAGE_NAME_PATTERNS:
            key = language.lower()
            if key in seen:
                continue
            if pattern.search(text):
                seen.add(key)
                result.append(language)
        return result

    def _run_patterns(
        self,
        patterns: list[tuple[re.Pattern[str], str]],
        text: str,
    ) -> list[str]:
        """Return matched labels, deduplicated, in match order."""
        seen: set[str] = set()
        result: list[str] = []
        for pattern, label in patterns:
            if label.lower() in seen:
                continue
            if pattern.search(text):
                seen.add(label.lower())
                result.append(label)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1: LLMEntityExtractor  (primary)
# ─────────────────────────────────────────────────────────────────────────────

# Regex to strip accidental markdown fences from LLM response
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


class LLMEntityExtractor:
    """LLM-backed structured classifier with regex fallback (Vertex AI / Gemini)."""

    def __init__(self, fallback: EntityExtractor | None = None):
        from app.core.config import settings

        self._model: GenerativeModel | None = None
        self._fallback = fallback or RegexEntityExtractor()

        # Allow local/dev credentials to be supplied via .env without shell setup.
        if settings.GCP_CREDENTIALS_PATH and not os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        ):
            configured_path = Path(settings.GCP_CREDENTIALS_PATH).expanduser()
            if not configured_path.is_absolute():
                repo_root = Path(__file__).resolve().parents[3]
                configured_path = repo_root / configured_path
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(configured_path)

        try:
            vertexai.init(
                project=settings.GCP_PROJECT_ID,
                location=settings.GCP_LOCATION,
            )
            self._model = GenerativeModel(
                model_name="gemini-2.0-flash",
                system_instruction=_SYSTEM_PROMPT,
            )
        except Exception:
            logger.warning(
                "Vertex AI init failed. Falling back to regex extraction.",
                exc_info=True,
            )

    def extract(
        self,
        files: list[str],
        commit_messages: list[str],
        title: str,
        body: str,
        labels: list[str],
    ) -> ExtractedEntities:
        # LLM unavailable (Vertex AI not configured / init failed) → regex last resort.
        if self._model is None:
            logger.info(
                "KG extractor: Vertex AI unavailable, using regex fallback for title='%s'",
                (title or "")[:120],
            )
            return _validate_against_taxonomy(
                self._fallback.extract(files, commit_messages, title, body, labels)
            )

        # Primary path: LLM extracts, taxonomy validates. No regex merging.
        try:
            context = _build_pr_context(files, commit_messages, title, body, labels)
            llm_result = self._call_llm(context)
            validated = _validate_against_taxonomy(llm_result)
            logger.info(
                "KG extractor LLM result for title='%s': languages=%d frameworks=%d domains=%d skills=%d tools=%d",
                (title or "")[:120],
                len(validated.languages),
                len(validated.frameworks),
                len(validated.domains),
                len(validated.skills),
                len(validated.tools),
            )
            logger.debug("KG extractor entities: %s", validated.to_dict())
            return validated
        except json.JSONDecodeError as exc:
            logger.warning(
                "KG extractor LLM JSON parse failed: %s — using regex fallback", exc
            )
        except Exception as exc:
            logger.warning(
                "KG extractor LLM call failed: %s — using regex fallback", exc
            )

        # LLM call failed at runtime → regex as last resort.
        return _validate_against_taxonomy(
            self._fallback.extract(files, commit_messages, title, body, labels)
        )

    def _call_llm(self, context: str) -> ExtractedEntities:
        """Call Gemini Flash via Vertex AI with the taxonomy system prompt."""
        if self._model is None:
            raise RuntimeError("Vertex AI model is not initialized")

        response = self._model.generate_content(
            context,
            generation_config={
                "max_output_tokens": 512,
                "temperature": 0.0,
                "response_mime_type": "application/json",
            },
        )

        # Extract text from response
        raw = response.text

        # Strip accidental markdown fences
        fence_match = _FENCE_RE.match(raw.strip())
        if fence_match:
            raw = fence_match.group(1)

        data = json.loads(raw)

        return ExtractedEntities(
            languages=_as_list(data.get("languages")),
            frameworks=_as_list(data.get("frameworks")),
            domains=_as_list(data.get("domains")),
            skills=_as_list(data.get("skills")),
            tools=_as_list(data.get("tools")),
        )
