import json
import re
from pathlib import Path
from typing import Any

from .result_checker import final_chapter_is_ready


PROJECT_ID = "book_001"
ACTIVE_PROJECT_FILE = "current_project.txt"
CHAPTER_RE = re.compile(r"ch(\d{3})_(draft|edited|final)\.md$")
REVIEW_RE = re.compile(r"ch(\d{3})_continuity\.md$")


def default_state(
    title: str = "Untitled Book",
    genre: str = "미정",
    project_id: str = PROJECT_ID,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "title": title,
        "genre": genre,
        "phase": "created",
        "current_chapter": 1,
        "total_chapters": None,
        "completed_chapters": [],
        "mode": "dummy",
        "artifacts": {},
        "chapter_artifacts": {},
        "decisions": [],
        "runs": [],
    }


def ensure_project(
    project_dir: Path,
    title: str = "Untitled Book",
    genre: str = "미정",
    project_id: str | None = None,
) -> dict[str, Any]:
    project_dir.mkdir(parents=True, exist_ok=True)
    for child in ["chapters", "reviews", "summaries", "final"]:
        (project_dir / child).mkdir(parents=True, exist_ok=True)

    project_file = project_dir / "project.json"
    if project_file.exists():
        return load_project(project_dir)

    state = default_state(
        title=title,
        genre=genre,
        project_id=project_id or project_dir.name or PROJECT_ID,
    )
    save_project(project_dir, state)
    return state


def list_projects(projects_dir: Path) -> list[str]:
    if not projects_dir.exists():
        return []
    project_ids = []
    for child in projects_dir.iterdir():
        if child.is_dir() and (child / "project.json").exists():
            project_ids.append(child.name)
    return sorted(project_ids)


def get_active_project_dir(projects_dir: Path) -> Path:
    active_id = load_active_project_id(projects_dir)
    return projects_dir / active_id


def load_active_project_id(projects_dir: Path) -> str:
    active_file = projects_dir / ACTIVE_PROJECT_FILE
    if active_file.exists():
        active_id = active_file.read_text(encoding="utf-8-sig").strip()
        if active_id and (projects_dir / active_id / "project.json").exists():
            return active_id

    project_ids = list_projects(projects_dir)
    if PROJECT_ID in project_ids:
        return PROJECT_ID
    if project_ids:
        return project_ids[0]
    return PROJECT_ID


def save_active_project_id(projects_dir: Path, project_id: str) -> None:
    project_dir = projects_dir / project_id
    if not (project_dir / "project.json").exists():
        raise ValueError(f"Unknown project: {project_id}")
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / ACTIVE_PROJECT_FILE).write_text(project_id + "\n", encoding="utf-8")


def create_project(projects_dir: Path, *, title: str, genre: str) -> tuple[Path, dict[str, Any]]:
    projects_dir.mkdir(parents=True, exist_ok=True)
    project_id = next_project_id(projects_dir)
    project_dir = projects_dir / project_id
    state = ensure_project(project_dir, title=title, genre=genre, project_id=project_id)
    return project_dir, state


def next_project_id(projects_dir: Path) -> str:
    highest = 0
    for project_id in list_projects(projects_dir):
        prefix, _, suffix = project_id.partition("_")
        if prefix == "book" and suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"book_{highest + 1:03d}"


def load_project(project_dir: Path) -> dict[str, Any]:
    project_file = project_dir / "project.json"
    if not project_file.exists():
        return ensure_project(project_dir)
    state = json.loads(project_file.read_text(encoding="utf-8-sig"))
    return normalize_project_state(project_dir, state)


def save_project(project_dir: Path, state: dict[str, Any]) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / "project.json"
    normalize_project_state(project_dir, state)
    project_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_after_run(
    project_dir: Path,
    state: dict[str, Any],
    *,
    phase: str,
    artifact_key: str,
    artifact_path: Path,
    run_record: dict[str, Any],
) -> dict[str, Any]:
    state["phase"] = phase
    artifact_posix = artifact_path.as_posix()
    state.setdefault("artifacts", {})[artifact_key] = artifact_posix
    chapter_number = chapter_number_from_path(artifact_path)
    if chapter_number is not None:
        chapter_key = chapter_id(chapter_number)
        state.setdefault("chapter_artifacts", {}).setdefault(chapter_key, {})[
            artifact_key
        ] = artifact_posix
        state["current_chapter"] = chapter_number
        if artifact_key == "finalizer" and final_chapter_is_ready(
            project_dir / "chapters" / f"{chapter_key}_final.md"
        ):
            completed = set(state.get("completed_chapters", []))
            completed.add(chapter_number)
            state["completed_chapters"] = sorted(completed)

    state.setdefault("runs", []).append(run_record)
    normalize_project_state(project_dir, state)
    save_project(project_dir, state)
    return state


def normalize_project_state(project_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    state.setdefault("phase", "created")
    state.setdefault("current_chapter", 1)
    state.setdefault("total_chapters", None)
    state.setdefault("completed_chapters", [])
    state.setdefault("mode", "dummy")
    state.setdefault("artifacts", {})
    state.setdefault("chapter_artifacts", {})
    state.setdefault("decisions", [])
    state.setdefault("runs", [])

    detected_total = detect_total_chapters(project_dir)
    if detected_total:
        state["total_chapters"] = detected_total

    completed = set(_detect_completed_chapters(project_dir))
    for chapter in state.get("completed_chapters", []):
        number = int(chapter)
        final_path = project_dir / "chapters" / f"{chapter_id(number)}_final.md"
        if final_chapter_is_ready(final_path):
            completed.add(number)
    state["completed_chapters"] = sorted(completed)

    current = int(state.get("current_chapter") or 1)
    total = state.get("total_chapters")
    if total is not None:
        total_int = int(total)
        for number in range(1, total_int + 1):
            if number not in completed:
                current = min(current, number)
                break
    if state.get("phase") == "finalized" and completed:
        next_chapter = max(completed) + 1
        if total is None or next_chapter <= int(total):
            current = max(current, next_chapter)
    state["current_chapter"] = current
    return state


def chapter_id(chapter_number: int) -> str:
    return f"ch{chapter_number:03d}"


def chapter_number_from_path(path: Path) -> int | None:
    name = path.name
    match = CHAPTER_RE.match(name) or REVIEW_RE.match(name)
    if not match:
        return None
    return int(match.group(1))


def detect_total_chapters(project_dir: Path) -> int | None:
    outline = project_dir / "outline.md"
    if not outline.exists():
        return None
    chapter_numbers: list[int] = []
    for line in outline.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"\|\s*(\d+)\s*\|", line)
        if match:
            chapter_numbers.append(int(match.group(1)))
    if chapter_numbers:
        return max(chapter_numbers)
    return None


def write_project_status(project_dir: Path, state: dict[str, Any]) -> Path:
    normalize_project_state(project_dir, state)
    status_file = project_dir / "project_status.md"
    status_file.write_text(build_project_status_text(project_dir, state), encoding="utf-8")
    return status_file


def build_project_status_text(project_dir: Path, state: dict[str, Any]) -> str:
    total = state.get("total_chapters") or "미정"
    current = int(state.get("current_chapter") or 1)
    completed = set(int(chapter) for chapter in state.get("completed_chapters", []))
    lines = [
        "# Project Status",
        "",
        "## Summary",
        f"- project_id: {state.get('project_id', project_dir.name)}",
        f"- title: {state.get('title', 'Untitled Book')}",
        f"- genre: {state.get('genre', '미정')}",
        f"- phase: {state.get('phase', 'created')}",
        f"- total_chapters: {total}",
        f"- completed_chapters: {', '.join(chapter_id(ch) for ch in sorted(completed)) or '없음'}",
        f"- next_chapter: {chapter_id(current)}",
        "",
        "## Chapter Progress",
        "| chapter | title | status | draft | edited | review | final |",
        "|---|---|---|---|---|---|---|",
    ]
    for number, title in _chapter_rows(project_dir):
        cid = chapter_id(number)
        draft = _yes_no(project_dir / "chapters" / f"{cid}_draft.md")
        edited = _yes_no(project_dir / "chapters" / f"{cid}_edited.md")
        review = _yes_no(project_dir / "reviews" / f"{cid}_continuity.md")
        final = _final_status_label(project_dir / "chapters" / f"{cid}_final.md")
        status = "done" if number in completed else ("current" if number == current else "pending")
        lines.append(f"| {cid} | {title} | {status} | {draft} | {edited} | {review} | {final} |")
    lines.extend(
        [
            "",
            "## Next Files",
            f"- draft: chapters/{chapter_id(current)}_draft.md",
            f"- edited: chapters/{chapter_id(current)}_edited.md",
            f"- review: reviews/{chapter_id(current)}_continuity.md",
            f"- final: chapters/{chapter_id(current)}_final.md",
            "",
        ]
    )
    return "\n".join(lines)


def _detect_completed_chapters(project_dir: Path) -> list[int]:
    chapters_dir = project_dir / "chapters"
    if not chapters_dir.exists():
        return []
    completed = []
    for path in chapters_dir.glob("ch*_final.md"):
        chapter_number = chapter_number_from_path(path)
        if chapter_number is not None and final_chapter_is_ready(path):
            completed.append(chapter_number)
    return sorted(completed)


def _chapter_rows(project_dir: Path) -> list[tuple[int, str]]:
    outline = project_dir / "outline.md"
    rows: list[tuple[int, str]] = []
    if outline.exists():
        for line in outline.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
            if match:
                rows.append((int(match.group(1)), match.group(2).strip()))
    if rows:
        return rows
    total = detect_total_chapters(project_dir) or 1
    return [(number, "") for number in range(1, total + 1)]


def _yes_no(path: Path) -> str:
    return "yes" if path.exists() and path.stat().st_size > 0 else "no"


def _final_status_label(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "no"
    return "yes" if final_chapter_is_ready(path) else "blocked"
