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
    action: WorkflowAction,
    state: dict[str, Any],
    user_request: str = "",
) -> BuiltTask:
    root = root.resolve()
    task_file = root / "tasks" / "current_task.md"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    history_dir = root / "tasks" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    expected_output = root / action.output_path
    prompt_path = Path("prompts") / action.prompt_file
    prompt_text = _read_optional(root / prompt_path, "역할 카드가 아직 없습니다.")
    input_files = _input_files_for(action.menu)
    artifacts = state.get("artifacts", {})

    task_text = f"""# AI 글쓰기 회사 작업지시서

## 목표
{action.goal}

## 직원 역할
- 역할: {action.role}
- 역할 카드: {prompt_path.as_posix()}

```text
{prompt_text.strip()}
```

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

- {action.output_path.as_posix()}

## 금지사항
- OpenAI API 키나 외부 API 호출을 요구하지 않는다.
- 지정된 출력 파일 밖에 원고 산출물을 흩뿌리지 않는다.
- 사용자의 금지 소재나 금지 표현이 있으면 반드시 따른다.
- 모르는 내용을 사실처럼 확정하지 말고 가정이라고 표시한다.

## 완료 조건
- 출력 파일 `{action.output_path.as_posix()}`가 존재한다.
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


def _input_files_for(menu: str) -> list[Path]:
    files = {
        "2": [],
        "3": [Path("projects/book_001/story_bible.md")],
        "4": [Path("projects/book_001/story_bible.md"), Path("projects/book_001/outline.md")],
        "5": [Path("projects/book_001/chapters/ch001_draft.md")],
        "6": [Path("projects/book_001/story_bible.md"), Path("projects/book_001/chapters/ch001_edited.md")],
        "7": [
            Path("projects/book_001/chapters/ch001_edited.md"),
            Path("projects/book_001/reviews/ch001_continuity.md"),
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
