from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .workflow import WorkflowAction


@dataclass(frozen=True)
class BuiltTask:
    task_file: Path
    expected_output: Path
    role: str
    menu: str
    label: str


def build_task(
    *,
    root: Path,
    project_dir: Path,
    action: WorkflowAction,
    state: dict[str, Any],
    user_request: str = "",
) -> BuiltTask:
    root = root.resolve()
    project_id = state.get("project_id", project_dir.name)
    task_file = root / "tasks" / "current_task.md"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    history_dir = root / "tasks" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    output_path = _project_output_path(action.output_path, project_id)
    expected_output = root / output_path
    prompt_path = Path("prompts") / action.prompt_file
    prompt_text = _read_optional(root / prompt_path, "역할 카드가 아직 없습니다.")
    input_files = _input_files_for(action.menu, project_id)
    artifacts = state.get("artifacts", {})

    task_text = f"""# AI 글쓰기 회사 작업지시서

## 목표
{action.goal}

## 직원 역할
- 역할: {action.role}
- 역할 카드: {prompt_path.as_posix()}

{_fenced_code_block(prompt_text.strip(), "text")}

## CEO 요청
{user_request.strip() or "추가 요청 없음"}

## 현재 프로젝트 상태
- project_id: {state.get("project_id", "book_001")}
- title: {state.get("title", "Untitled Book")}
- genre: {state.get("genre", "미정")}
- phase: {state.get("phase", "created")}
- current_chapter: {state.get("current_chapter", 1)}

## 입력 파일
{_format_input_files(root, input_files)}

## 기존 산출물
{_format_artifacts(artifacts)}

## 출력 파일
반드시 아래 파일 하나를 생성하거나 갱신한다.

- {output_path.as_posix()}

## 금지사항
- OpenAI API 키나 외부 API 호출을 요구하지 않는다.
- 지정된 출력 파일 밖에 원고 산출물을 흩뿌리지 않는다.
- 사용자의 금지 소재나 금지 표현이 있으면 반드시 따른다.
- 모르는 내용을 사실처럼 확정하지 말고 가정이라고 표시한다.

## 완료 조건
- 출력 파일 `{output_path.as_posix()}`가 존재한다.
- 결과물 첫 부분에 이번 작업의 목적과 사용한 입력 파일을 짧게 적는다.
- 다음 단계 진행에 필요한 메모를 마지막에 `다음 작업 메모`로 남긴다.
"""
    task_file.write_text(task_text, encoding="utf-8")

    history_file = history_dir / f"{action.menu}_{action.role}_task.md"
    history_file.write_text(task_text, encoding="utf-8")

    return BuiltTask(
        task_file=task_file,
        expected_output=expected_output,
        role=action.role,
        menu=action.menu,
        label=action.label,
    )


def _read_optional(path: Path, fallback: str) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return fallback


def _fenced_code_block(text: str, language: str = "") -> str:
    longest_tick_run = 0
    current_run = 0
    for char in text:
        if char == "`":
            current_run += 1
            longest_tick_run = max(longest_tick_run, current_run)
        else:
            current_run = 0

    fence = "`" * max(3, longest_tick_run + 1)
    language_suffix = language if language else ""
    return f"{fence}{language_suffix}\n{text}\n{fence}"


def _project_output_path(output_path: Path, project_id: str) -> Path:
    parts = output_path.parts
    if len(parts) >= 2 and parts[0] == "projects":
        return Path(parts[0]) / project_id / Path(*parts[2:])
    return output_path


def _input_files_for(menu: str, project_id: str = "book_001") -> list[Path]:
    project_root = Path("projects") / project_id
    files = {
        "2": [],
        "3": [project_root / "story_bible.md"],
        "4": [project_root / "story_bible.md", project_root / "outline.md"],
        "5": [project_root / "chapters" / "ch001_draft.md"],
        "6": [project_root / "story_bible.md", project_root / "chapters" / "ch001_edited.md"],
        "7": [
            project_root / "chapters" / "ch001_edited.md",
            project_root / "reviews" / "ch001_continuity.md",
        ],
    }
    return files.get(menu, [])


def _format_input_files(root: Path, files: list[Path]) -> str:
    if not files:
        return "- 없음. CEO 요청과 현재 프로젝트 상태를 기준으로 작성한다."
    lines = []
    for file_path in files:
        status = "있음" if (root / file_path).exists() else "없음"
        lines.append(f"- {file_path.as_posix()} ({status})")
    return "\n".join(lines)


def _format_artifacts(artifacts: dict[str, str]) -> str:
    if not artifacts:
        return "- 아직 등록된 산출물이 없다."
    return "\n".join(f"- {key}: {value}" for key, value in sorted(artifacts.items()))
