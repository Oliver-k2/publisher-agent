import json
from pathlib import Path
from typing import Any


PROJECT_ID = "book_001"
ACTIVE_PROJECT_FILE = "current_project.txt"


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
        "mode": "dummy",
        "artifacts": {},
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
    return json.loads(project_file.read_text(encoding="utf-8-sig"))


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
