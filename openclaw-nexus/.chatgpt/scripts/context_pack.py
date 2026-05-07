#!/usr/bin/env python3
"""Create a compact ChatGPT context pack for OpenClaw Nexus.

The script is intentionally dependency-free. It helps an assistant load only the
relevant ChatGPT skill and high-signal project state snippets instead of reading
all `.chatgpt` files eagerly.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT_MARKERS = (".chatgpt", "README.md")
DEFAULT_MAX_SECTION_LINES = 90
DEFAULT_MAX_STATE_LINES = 120

SKILL_HINTS = {
    "concept-refinement": (
        "konzept", "concept", "zielbild", "scope", "nicht-ziele",
        "nichtziele", "verfeiner", "schärf", "schaerf", "produktlogik",
        "authority", "systemgrenze", "begriffe", "akzeptanzkriterien",
    ),
    "system-analysis": (
        "systemanalyse", "system analyse", "system-analysis", "gesamtanalyse",
        "gesamtsystem", "bewert", "bewertung", "scorecard", "audit",
        "review", "reifegrad", "architekturreview", "qualität", "qualitaet",
        "schwachstellen", "risikoanalyse", "system review",
    ),
    "drift": (
        "drift", "kurs", "konsistent", "konsistenz", "current_state", "status",
        "zielbild", "realität", "realitaet", "abweich", "doku", "documentation",
    ),
    "legacy": (
        "legacy", "altlast", "alt", "toter code", "dead code", "platzhalter",
        "unnötig", "unnoetig", "entfernen", "kompatibilität", "kompatibilitaet",
        "archiv", "doppel", "veraltet",
    ),
    "leverage": (
        "leverage", "produktionsreif", "production", "readiness", "betrieb",
        "größter hebel", "groesster hebel", "größten hebel", "groessten hebel",
        "wichtigster punkt", "risiko", "reife", "prod",
    ),
    "sprint-workflow": (
        "sprint", "phase", "phases", "arbeitsplan", "nächste phase",
        "naechste phase", "clear sprint", "sprintabschluss",
    ),
}

HIGH_SIGNAL_PATHS = (
    "README.md",
    ".chatgpt/README.md",
    ".chatgpt/state/CURRENT_STATE.md",
    ".chatgpt/state/phases.md",
    "pytest.ini",
    "scripts/validate_project.py",
    "scripts/run_tests.sh",
    "scripts/package_project.py",
    "nexus/blueprint.yml",
    "nexus/policies.yml",
    "nexus/runtime-tools.yml",
)


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path
    description: str
    body: str


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if all((candidate / marker).exists() for marker in ROOT_MARKERS):
            return candidate
    raise SystemExit("Could not locate repo root containing .chatgpt and README.md")


def read_text(path: Path, max_chars: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n... [truncated]"
    return text


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip().splitlines()
    meta: dict[str, str] = {}
    for line in raw:
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        meta[key.strip()] = value
    return meta, text[end + 5 :].lstrip()


def load_skills(root: Path) -> list[Skill]:
    skills_dir = root / ".chatgpt" / "skills"
    skills: list[Skill] = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        text = read_text(skill_file)
        meta, body = parse_frontmatter(text)
        name = meta.get("name") or skill_file.parent.name
        description = meta.get("description", "")
        skills.append(Skill(name=name, path=skill_file, description=description, body=body))
    return skills


def score_skill(skill: Skill, query: str) -> int:
    q = query.lower()
    score = 0
    if skill.name.lower() in q:
        score += 10
    for hint in SKILL_HINTS.get(skill.name, ()):  # exact project skill hints
        if hint.lower() in q:
            score += 3
    for token in re.findall(r"[\wäöüÄÖÜß-]{4,}", skill.description.lower()):
        if token in q:
            score += 1
    return score


def select_skill(skills: list[Skill], requested: str | None, query: str | None) -> Skill | None:
    if requested:
        for skill in skills:
            if skill.name == requested:
                return skill
        raise SystemExit(f"Unknown skill: {requested}")
    if not query:
        return None
    ranked = sorted(((score_skill(skill, query), skill) for skill in skills), reverse=True, key=lambda x: x[0])
    return ranked[0][1] if ranked and ranked[0][0] > 0 else None


def first_sections(markdown: str, max_lines: int) -> str:
    lines = markdown.splitlines()
    if len(lines) <= max_lines:
        return markdown.strip()
    return "\n".join(lines[:max_lines]).rstrip() + "\n... [skill body truncated; open SKILL.md if more detail is needed]"


def markdown_headings(text: str, max_items: int = 24) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            headings.append(line.strip())
            if len(headings) >= max_items:
                break
    return headings


def grep_paths(root: Path, patterns: Iterable[str], include: tuple[str, ...] = ("*.py", "*.md", "*.yml", "*.yaml", "*.toml", "*.sh"), limit: int = 80) -> list[str]:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    skip_parts = {".git", ".venv", "__pycache__", ".pytest_cache", "docs/archiv"}
    hits: list[str] = []
    for glob in include:
        for path in sorted(root.rglob(glob)):
            rel = path.relative_to(root).as_posix()
            if any(part in rel for part in skip_parts):
                continue
            text = read_text(path, max_chars=200_000)
            if any(pattern.search(text) or pattern.search(rel) for pattern in compiled):
                hits.append(rel)
                if len(hits) >= limit:
                    return hits
    return hits


def file_inventory(root: Path) -> str:
    buckets = {
        "chatgpt_skills": list((root / ".chatgpt" / "skills").glob("*/SKILL.md")),
        "tests": list((root / "tests").glob("test_*.py")),
        "scripts": list((root / "scripts").glob("*")),
        "nexus_config": list((root / "nexus").glob("*.yml")),
        "python_packages": list((root / "nexusctl").rglob("*.py")),
    }
    lines = []
    for name, files in buckets.items():
        lines.append(f"- {name}: {len(files)}")
    return "\n".join(lines)


def state_excerpt(root: Path, max_lines: int) -> str:
    parts: list[str] = []
    for rel in (".chatgpt/state/CURRENT_STATE.md", ".chatgpt/state/phases.md"):
        path = root / rel
        text = read_text(path)
        if not text:
            parts.append(f"### {rel}\n[missing]")
            continue
        headings = markdown_headings(text)
        lines = text.splitlines()
        excerpt = "\n".join(lines[:max_lines]).rstrip()
        if len(lines) > max_lines:
            excerpt += "\n... [state truncated]"
        parts.append(f"### {rel}\nHeadings:\n" + "\n".join(f"- {h}" for h in headings) + "\n\nExcerpt:\n" + excerpt)
    return "\n\n".join(parts)


def print_list(skills: list[Skill]) -> None:
    print("# Available ChatGPT skills\n")
    for skill in skills:
        print(f"- `{skill.name}` — {skill.description}")


def build_pack(root: Path, skill: Skill | None, query: str | None, mode: str, max_skill_lines: int, max_state_lines: int) -> str:
    lines: list[str] = []
    lines.append("# ChatGPT Context Pack")
    lines.append("")
    lines.append(f"Repository: `{root.name}`")
    if query:
        lines.append(f"Query: {query}")
    lines.append("")
    lines.append("## Project inventory")
    lines.append(file_inventory(root))
    lines.append("")

    if skill:
        lines.append("## Selected skill")
        lines.append(f"- Name: `{skill.name}`")
        lines.append(f"- Path: `{skill.path.relative_to(root).as_posix()}`")
        lines.append(f"- Description: {skill.description}")
        lines.append("")
        lines.append("### Skill instructions")
        if mode == "full":
            lines.append(skill.body.strip())
        else:
            lines.append(first_sections(skill.body, max_skill_lines))
        lines.append("")
    else:
        lines.append("## Selected skill")
        lines.append("No skill selected. Use `--skill <name>` or `--query <text>`.")
        lines.append("")

    lines.append("## State signal")
    lines.append(state_excerpt(root, max_state_lines if mode == "full" else min(max_state_lines, 80)))
    lines.append("")

    lines.append("## High-signal files")
    for rel in HIGH_SIGNAL_PATHS:
        path = root / rel
        if path.exists():
            line_count = len(read_text(path).splitlines())
            lines.append(f"- `{rel}` ({line_count} lines)")
    lines.append("")

    if query:
        terms = [re.escape(t) for t in re.findall(r"[\wäöüÄÖÜß-]{5,}", query.lower())[:8]]
        if terms:
            hits = grep_paths(root, terms, limit=50)
            lines.append("## Query-related file hints")
            if hits:
                lines.extend(f"- `{hit}`" for hit in hits)
            else:
                lines.append("- No direct keyword hits found.")
            lines.append("")

    lines.append("## Suggested next read")
    if skill:
        if skill.name == "concept-refinement":
            lines.append("Start from product overview and CURRENT_STATE; sharpen goal, scope, authority boundaries, acceptance criteria, and the next decision.")
        elif skill.name == "system-analysis":
            lines.append("Start from README, CURRENT_STATE, nexus contracts, tests, scripts, and nexusctl structure; build a scorecard with strengths, risks, and prioritized improvements.")
        elif skill.name == "drift":
            lines.append("Read only the specific status claims being checked, then verify them against code/tests/config.")
        elif skill.name == "legacy":
            lines.append("Start from suspected files or historical terms; verify usage before recommending removal.")
        elif skill.name == "leverage":
            lines.append("Extract production risks from CURRENT_STATE and tests, rank candidates, then name exactly one main lever.")
        elif skill.name == "sprint-workflow":
            lines.append("Use phases.md as the active plan and keep CURRENT_STATE unchanged until closing the sprint.")
    else:
        lines.append("Select a skill or read .chatgpt/README.md.")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a compact context pack for ChatGPT skills.")
    parser.add_argument("--root", default=".", help="Repository root or path inside the repository.")
    parser.add_argument("--list-skills", action="store_true", help="List available skills and exit.")
    parser.add_argument("--skill", help="Skill name to load explicitly, e.g. concept-refinement, system-analysis, drift, legacy, leverage.")
    parser.add_argument("--query", help="Natural-language user request used to auto-select a skill and show file hints.")
    parser.add_argument("--mode", choices=("compact", "full"), default="compact", help="How much skill/state content to include.")
    parser.add_argument("--max-skill-lines", type=int, default=DEFAULT_MAX_SECTION_LINES)
    parser.add_argument("--max-state-lines", type=int, default=DEFAULT_MAX_STATE_LINES)
    args = parser.parse_args(argv)

    root = find_repo_root(Path(args.root))
    skills = load_skills(root)

    if args.list_skills:
        print_list(skills)
        return 0

    skill = select_skill(skills, args.skill, args.query)
    print(build_pack(root, skill, args.query, args.mode, args.max_skill_lines, args.max_state_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
