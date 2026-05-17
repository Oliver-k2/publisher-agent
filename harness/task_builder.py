from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .result_checker import final_chapter_is_ready
from .state_manager import chapter_id
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
    chapter_number = int(state.get("current_chapter") or 1)
    current_chapter_id = chapter_id(chapter_number)
    task_file = root / "tasks" / "current_task.md"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    history_dir = root / "tasks" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    output_path = _project_output_path(action.output_path, project_id, current_chapter_id)
    expected_output = root / output_path
    prompt_path = Path("prompts") / action.prompt_file
    prompt_text = _read_optional(root / prompt_path, "역할 카드가 아직 없습니다.")
    input_files = _input_files_for(root, action.menu, project_id, current_chapter_id)
    artifacts = state.get("artifacts", {})
    chapter_artifacts = state.get("chapter_artifacts", {})
    completed_chapters = state.get("completed_chapters", [])
    chapter_assignment = _chapter_assignment(root, project_id, chapter_number)
    blocked_previous_note = _blocked_previous_final_note(root, project_id, current_chapter_id)

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
- current_chapter: {chapter_number}
- current_chapter_id: {current_chapter_id}
- total_chapters: {state.get("total_chapters") or "미정"}
- completed_chapters: {", ".join(chapter_id(int(ch)) for ch in completed_chapters) or "없음"}

## 이번 챕터 작업 기준
- 이번 작업은 반드시 `{current_chapter_id}` 챕터를 대상으로 한다.
- 챕터 산출물은 `{output_path.as_posix()}` 하나에 저장한다.
- 목차의 Chapter Table에서 `{chapter_number}`장 행과 이전 챕터의 `Next Handoff`를 우선 확인한다.
- 이전 최종본이 있으면 인물 감정선, 시간선, 말투, 미해결 떡밥을 이어받는다.
- 이전 챕터 최종본이 `final_status: BLOCKED`이면 정상 canon으로 쓰지 말고, 이전 편집본과 continuity report의 판독 가능한 요약만 연결 근거로 삼는다.
- 상세 장면 브리프가 없더라도 아래 `현재 챕터 할당`과 story_bible/outline의 canon을 근거로 장면을 구성한다.
- 새 고유명사, 새 backstory, 범죄 수법 세부처럼 canon을 바꾸는 내용은 만들지 않는다. 그러나 장소의 동선, 대화, 장면 순서, 감각 묘사 같은 실행 디테일은 합리적으로 설계해도 된다.
{blocked_previous_note}

## 현재 챕터 할당
{chapter_assignment}

## 입력 파일
{_format_input_files(root, input_files)}

## 기존 산출물
{_format_artifacts(artifacts)}

## 챕터별 산출물
{_format_chapter_artifacts(chapter_artifacts)}

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


def _project_output_path(output_path: Path, project_id: str, current_chapter_id: str) -> Path:
    parts = output_path.parts
    if len(parts) >= 2 and parts[0] == "projects":
        projected = Path(parts[0]) / project_id / Path(*parts[2:])
    else:
        projected = output_path
    return Path(str(projected).replace("ch001", current_chapter_id))


def _input_files_for(
    root: Path,
    menu: str,
    project_id: str = "book_001",
    current_chapter_id: str = "ch001",
) -> list[Path]:
    project_root = Path("projects") / project_id
    previous_chapter_number = max(1, int(current_chapter_id[2:]) - 1)
    previous_chapter_id = chapter_id(previous_chapter_number)
    previous_final = project_root / "chapters" / f"{previous_chapter_id}_final.md"
    previous_edited = project_root / "chapters" / f"{previous_chapter_id}_edited.md"
    previous_review = project_root / "reviews" / f"{previous_chapter_id}_continuity.md"
    previous_chapter_context = [previous_final]
    if current_chapter_id != "ch001" and not final_chapter_is_ready(root / previous_final):
        previous_chapter_context = [
            path for path in [previous_edited, previous_review] if (root / path).exists()
        ]
    files = {
        "2": [],
        "3": [project_root / "story_bible.md"],
        "4": [
            project_root / "story_bible.md",
            project_root / "outline.md",
            *previous_chapter_context,
        ],
        "5": [
            project_root / "story_bible.md",
            project_root / "outline.md",
            project_root / "chapters" / f"{current_chapter_id}_draft.md",
            project_root / "reviews" / f"{current_chapter_id}_continuity.md",
        ],
        "6": [
            project_root / "story_bible.md",
            project_root / "outline.md",
            project_root / "chapters" / f"{current_chapter_id}_edited.md",
        ],
        "7": [
            project_root / "chapters" / f"{current_chapter_id}_edited.md",
            project_root / "reviews" / f"{current_chapter_id}_continuity.md",
        ],
    }
    input_files = files.get(menu, [])
    if current_chapter_id == "ch001":
        return [path for path in input_files if path != previous_final]
    return input_files


def _blocked_previous_final_note(root: Path, project_id: str, current_chapter_id: str) -> str:
    if current_chapter_id == "ch001":
        return ""
    previous_chapter_number = max(1, int(current_chapter_id[2:]) - 1)
    previous_chapter_id = chapter_id(previous_chapter_number)
    previous_final = Path("projects") / project_id / "chapters" / f"{previous_chapter_id}_final.md"
    final_path = root / previous_final
    if not final_path.exists() or final_chapter_is_ready(final_path):
        return ""
    previous_edited = Path("projects") / project_id / "chapters" / f"{previous_chapter_id}_edited.md"
    previous_review = Path("projects") / project_id / "reviews" / f"{previous_chapter_id}_continuity.md"
    return (
        "\n## 이전 챕터 최종본 주의\n"
        f"- `{previous_final.as_posix()}`는 존재하지만 READY 최종본이 아니다.\n"
        f"- 이 파일을 확정 원고로 이어받지 말고 `{previous_edited.as_posix()}`와 "
        f"`{previous_review.as_posix()}`의 판독 가능한 연결 정보, 그리고 outline의 Chapter Table을 우선한다.\n"
    )


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


def _format_chapter_artifacts(chapter_artifacts: dict[str, dict[str, str]]) -> str:
    if not chapter_artifacts:
        return "- 아직 등록된 챕터별 산출물이 없다."
    lines = []
    for chapter_key, artifacts in sorted(chapter_artifacts.items()):
        if not artifacts:
            continue
        joined = ", ".join(f"{key}: {value}" for key, value in sorted(artifacts.items()))
        lines.append(f"- {chapter_key}: {joined}")
    return "\n".join(lines) if lines else "- 아직 등록된 챕터별 산출물이 없다."


def _chapter_assignment(root: Path, project_id: str, chapter_number: int) -> str:
    outline = root / "projects" / project_id / "outline.md"
    if not outline.exists():
        return "- outline.md가 아직 없어 현재 챕터 표 행을 추출할 수 없다."

    lines = outline.read_text(encoding="utf-8", errors="replace").splitlines()
    header: list[str] | None = None
    for line in lines:
        cells = _markdown_table_cells(line)
        if not cells:
            continue
        if cells[0].lower() == "chapter":
            header = cells
            continue
        if not cells[0].isdigit() or int(cells[0]) != chapter_number:
            continue
        if header and len(header) == len(cells):
            return "\n".join(f"- {key}: {value}" for key, value in zip(header, cells))
        return "- " + " | ".join(cells)
    return f"- outline.md의 Chapter Table에서 {chapter_number}장 행을 찾지 못했다. 이 경우 전체 목차와 이전 챕터 최종본을 근거로 작업하고 Draft Notes에 위험을 남긴다."


def _markdown_table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if cells and all(set(cell) <= {"-", ":"} for cell in cells):
        return []
    return cells
