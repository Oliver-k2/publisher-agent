import json
from pathlib import Path
from typing import Any


PROJECT_ID = "book_001"


def default_state(title: str = "Untitled Book", genre: str = "미정") -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "title": title,
        "genre": genre,
        "phase": "created",
        "current_chapter": 1,
        "mode": "dummy",
        "artifacts": {},
        "decisions": [],
        "runs": [],
    }


def ensure_project(project_dir: Path, title: str = "Untitled Book", genre: str = "미정") -> dict[str, Any]:
    project_dir.mkdir(parents=True, exist_ok=True)
    for child in ["chapters", "reviews", "summaries", "final"]:
        (project_dir / child).mkdir(parents=True, exist_ok=True)

    project_file = project_dir / "project.json"
    if project_file.exists():
        return load_project(project_dir)

    state = default_state(title=title, genre=genre)
    save_project(project_dir, state)
    return state


def load_project(project_dir: Path) -> dict[str, Any]:
    project_file = project_dir / "project.json"
    if not project_file.exists():
        return ensure_project(project_dir)
    return json.loads(project_file.read_text(encoding="utf-8"))


def save_project(project_dir: Path, state: dict[str, Any]) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / "project.json"
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
    state.setdefault("artifacts", {})[artifact_key] = artifact_path.as_posix()
    state.setdefault("runs", []).append(run_record)
    save_project(project_dir, state)
    return state
