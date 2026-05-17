from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .codex_runner import run_codex
from .logger import append_run_log
from .result_checker import (
    check_result,
    continuity_allows_finalizer,
    create_correction_task,
    final_chapter_is_ready,
)
from .state_manager import (
    chapter_id,
    create_project,
    list_projects,
    load_project,
    save_active_project_id,
    save_project,
    update_after_run,
    write_project_status,
)
from .task_builder import build_task
from .workflow import WorkflowAction, get_action

MAX_STEP_ATTEMPTS = 2
MAX_QA_REPAIR_ATTEMPTS = 2


@dataclass(frozen=True)
class AutoRunSummary:
    success: bool
    project_dir: Path
    final_output: Path | None
    message: str
    completed_steps: list[str]


def run_full_automation(
    *,
    root: Path,
    projects_dir: Path,
    log_file: Path,
    ceo_request: str,
    active_project_dir: Path,
) -> AutoRunSummary:
    project_dir, state = _select_or_create_auto_project(
        projects_dir=projects_dir,
        active_project_dir=active_project_dir,
        ceo_request=ceo_request,
    )
    save_active_project_id(projects_dir, state["project_id"])
    _apply_auto_brief(state, ceo_request)
    save_project(project_dir, state)

    completed_steps: list[str] = []
    mode = state.get("mode", "dummy")

    if not _usable_file(project_dir / "production_plan.md"):
        producer = _run_custom_step(
            root=root,
            project_dir=project_dir,
            log_file=log_file,
            state=state,
            role="producer",
            menu="auto-producer",
            prompt_file="producer.md",
            label="자동 제작 지휘",
            goal=(
                "CEO의 최초 명령을 책 제작 전체의 운영 브리프로 바꾼다. "
                "분량, 형식, 장 수, 직원별 작업 순서, 완료 조건을 명확히 정리한다."
            ),
            output_path=project_dir / "production_plan.md",
            ceo_request=ceo_request,
            mode=mode,
        )
        completed_steps.append("producer")
        if not producer.success:
            return _failed(project_dir, completed_steps, producer.message)

        state = load_project(project_dir)
        state.setdefault("artifacts", {})["producer"] = producer.expected_output.relative_to(root).as_posix()
        save_project(project_dir, state)
    else:
        completed_steps.append("producer:reuse")
        state = load_project(project_dir)

    for menu in _missing_setup_menus(project_dir):
        result = _run_menu_step(
            root=root,
            project_dir=project_dir,
            log_file=log_file,
            state=state,
            menu=menu,
            ceo_request=ceo_request,
        )
        completed_steps.append(get_action(menu).role)
        if not result.success:
            return _failed(project_dir, completed_steps, result.message)
        state = load_project(project_dir)

    total_chapters = int(state.get("total_chapters") or state.get("auto_target_chapters") or 1)
    state["total_chapters"] = total_chapters
    save_project(project_dir, state)

    while len(state.get("completed_chapters", [])) < total_chapters:
        current = int(state.get("current_chapter") or 1)
        if current > total_chapters:
            break
        outline_result = _run_menu_step(
            root=root,
            project_dir=project_dir,
            log_file=log_file,
            state=state,
            menu="3",
            ceo_request=ceo_request,
        )
        completed_steps.append(f"outliner:{chapter_id(current)}")
        if not outline_result.success:
            return _failed(project_dir, completed_steps, outline_result.message)
        state = load_project(project_dir)

        for menu in ["4", "5", "6"]:
            result = _run_menu_step(
                root=root,
                project_dir=project_dir,
                log_file=log_file,
                state=state,
                menu=menu,
                ceo_request=ceo_request,
            )
            completed_steps.append(f"{get_action(menu).role}:{chapter_id(current)}")
            if not result.success:
                return _failed(project_dir, completed_steps, result.message)
            state = load_project(project_dir)

        review_path = project_dir / "reviews" / f"{chapter_id(current)}_continuity.md"
        repair_attempt = 0
        while not continuity_allows_finalizer(review_path):
            if repair_attempt >= MAX_QA_REPAIR_ATTEMPTS:
                create_correction_task(
                    root=root,
                    original_task=root / "tasks" / "current_task.md",
                    missing_output=review_path,
                )
                return _failed(
                    project_dir,
                    completed_steps,
                    f"continuity gate blocked finalizer after repair attempts: {review_path}",
                )
            repair_attempt += 1
            for menu in ["5", "6"]:
                result = _run_menu_step(
                    root=root,
                    project_dir=project_dir,
                    log_file=log_file,
                    state=state,
                    menu=menu,
                    ceo_request=ceo_request,
                )
                completed_steps.append(
                    f"{get_action(menu).role}:repair{repair_attempt}:{chapter_id(current)}"
                )
                if not result.success:
                    return _failed(project_dir, completed_steps, result.message)
                state = load_project(project_dir)

        result = _run_menu_step(
            root=root,
            project_dir=project_dir,
            log_file=log_file,
            state=state,
            menu="7",
            ceo_request=ceo_request,
        )
        completed_steps.append(f"{get_action('7').role}:{chapter_id(current)}")
        if not result.success:
            return _failed(project_dir, completed_steps, result.message)
        if not final_chapter_is_ready(project_dir / "chapters" / f"{chapter_id(current)}_final.md"):
            return _failed(
                project_dir,
                completed_steps,
                f"finalizer output is not READY: {project_dir / 'chapters' / f'{chapter_id(current)}_final.md'}",
            )
        state = load_project(project_dir)

    package = _run_packager(
        root=root,
        project_dir=project_dir,
        log_file=log_file,
        state=state,
        ceo_request=ceo_request,
        mode=mode,
    )
    completed_steps.append("packager")
    if not package.success:
        return _failed(project_dir, completed_steps, package.message)

    state = load_project(project_dir)
    state["phase"] = "packaged"
    state.setdefault("artifacts", {})["packager"] = package.expected_output.relative_to(root).as_posix()
    save_project(project_dir, state)
    write_project_status(project_dir, state)

    return AutoRunSummary(
        success=True,
        project_dir=project_dir,
        final_output=package.expected_output,
        message="완전자동화가 최종 원고 패키지까지 완료되었습니다.",
        completed_steps=completed_steps,
    )


@dataclass(frozen=True)
class _StepResult:
    success: bool
    expected_output: Path
    message: str


def _run_menu_step(
    *,
    root: Path,
    project_dir: Path,
    log_file: Path,
    state: dict[str, Any],
    menu: str,
    ceo_request: str,
) -> _StepResult:
    action = get_action(menu)
    task = build_task(
        root=root,
        project_dir=project_dir,
        action=action,
        state=state,
        user_request=_auto_request_for_step(state, ceo_request),
    )
    mode = state.get("mode", "dummy")
    last_message = ""
    record: dict[str, Any] | None = None
    for attempt in range(1, MAX_STEP_ATTEMPTS + 1):
        run = run_codex(
            root=root,
            task_file=task.task_file,
            expected_output=task.expected_output,
            role=task.role,
            mode=mode,
        )
        check = check_result(
            task.expected_output,
            newer_than=task.task_file.stat().st_mtime,
            role=task.role,
        )
        success = run.success and check.success
        message = run.message if success else f"{run.message}; {check.message}"
        if attempt > 1:
            message = f"retry {attempt}/{MAX_STEP_ATTEMPTS}: {message}"
        record = append_run_log(
            log_file=log_file,
            role=task.role,
            menu=task.menu,
            task_file=task.task_file,
            expected_output=task.expected_output,
            success=success,
            mode=mode,
            message=message,
        )
        if success:
            break
        last_message = message
    else:
        create_correction_task(root=root, original_task=task.task_file, missing_output=task.expected_output)
        return _StepResult(False, task.expected_output, last_message)

    if record is None:
        return _StepResult(False, task.expected_output, "internal error: missing run record")

    updated_state = update_after_run(
        project_dir,
        state,
        phase=action.phase,
        artifact_key=action.role,
        artifact_path=task.expected_output.relative_to(root),
        run_record=record,
    )
    write_project_status(project_dir, updated_state)
    return _StepResult(True, task.expected_output, message)


def _run_custom_step(
    *,
    root: Path,
    project_dir: Path,
    log_file: Path,
    state: dict[str, Any],
    role: str,
    menu: str,
    prompt_file: str,
    label: str,
    goal: str,
    output_path: Path,
    ceo_request: str,
    mode: str,
) -> _StepResult:
    action = WorkflowAction(
        menu=menu,
        label=label,
        role=role,
        prompt_file=prompt_file,
        goal=goal,
        output_path=output_path.relative_to(root),
        phase=state.get("phase", "created"),
        next_menu="auto",
    )
    task = build_task(
        root=root,
        project_dir=project_dir,
        action=action,
        state=state,
        user_request=_auto_request_for_step(state, ceo_request),
    )
    last_message = ""
    for attempt in range(1, MAX_STEP_ATTEMPTS + 1):
        run = run_codex(
            root=root,
            task_file=task.task_file,
            expected_output=task.expected_output,
            role=role,
            mode=mode,
        )
        check = check_result(task.expected_output, newer_than=task.task_file.stat().st_mtime, role=role)
        success = run.success and check.success
        message = run.message if success else f"{run.message}; {check.message}"
        if attempt > 1:
            message = f"retry {attempt}/{MAX_STEP_ATTEMPTS}: {message}"
        append_run_log(
            log_file=log_file,
            role=role,
            menu=menu,
            task_file=task.task_file,
            expected_output=task.expected_output,
            success=success,
            mode=mode,
            message=message,
        )
        if success:
            return _StepResult(True, task.expected_output, message)
        last_message = message

    create_correction_task(root=root, original_task=task.task_file, missing_output=task.expected_output)
    return _StepResult(False, task.expected_output, last_message)


def _run_packager(
    *,
    root: Path,
    project_dir: Path,
    log_file: Path,
    state: dict[str, Any],
    ceo_request: str,
    mode: str,
) -> _StepResult:
    output_path = project_dir / "final" / "book_final.md"
    total_chapters = int(state.get("total_chapters") or 1)
    final_files = [
        f"- projects/{project_dir.name}/chapters/{chapter_id(number)}_final.md"
        for number in range(1, total_chapters + 1)
    ]
    goal = (
        "완료된 최종 챕터들을 순서대로 묶어 한 권짜리 원고 패키지를 만든다.\n\n"
        "포함해야 할 최종 챕터 파일:\n" + "\n".join(final_files)
    )
    return _run_custom_step(
        root=root,
        project_dir=project_dir,
        log_file=log_file,
        state=state,
        role="packager",
        menu="auto-packager",
        prompt_file="packager.md",
        label="최종 원고 패키징",
        goal=goal,
        output_path=output_path,
        ceo_request=ceo_request,
        mode=mode,
    )


def _select_or_create_auto_project(
    *,
    projects_dir: Path,
    active_project_dir: Path,
    ceo_request: str,
) -> tuple[Path, dict[str, Any]]:
    requested_project = _project_from_request(projects_dir, ceo_request)
    if requested_project is not None:
        project_dir, state = requested_project
        return project_dir, state

    if _should_continue_active(active_project_dir, ceo_request):
        state = load_project(active_project_dir)
        return active_project_dir, state

    title = _infer_title(ceo_request)
    genre = _infer_genre(ceo_request)
    project_dir, state = create_project(projects_dir, title=title, genre=genre)
    active_state = load_project(active_project_dir) if (active_project_dir / "project.json").exists() else {}
    state["mode"] = active_state.get("mode", state.get("mode", "dummy"))
    return project_dir, state


def _project_from_request(
    projects_dir: Path,
    ceo_request: str,
) -> tuple[Path, dict[str, Any]] | None:
    for project_id in _project_ids_from_request(ceo_request):
        project_dir = projects_dir / project_id
        if (project_dir / "project.json").exists():
            return project_dir, load_project(project_dir)

    request = ceo_request.casefold()
    for project_id in list_projects(projects_dir):
        project_dir = projects_dir / project_id
        state = load_project(project_dir)
        title = str(state.get("title", "")).strip()
        if title and title.casefold() in request:
            return project_dir, state
    return None


def _project_ids_from_request(ceo_request: str) -> list[str]:
    project_ids: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\bbook[\s_-]*(\d{1,4})\b", ceo_request, flags=re.IGNORECASE):
        project_id = f"book_{int(match.group(1)):03d}"
        if project_id not in seen:
            project_ids.append(project_id)
            seen.add(project_id)
    return project_ids


def _should_continue_active(active_project_dir: Path, ceo_request: str) -> bool:
    project_file = active_project_dir / "project.json"
    if not project_file.exists():
        return False
    state = load_project(active_project_dir)
    title = str(state.get("title", "")).strip()
    request = ceo_request.casefold()
    continue_keywords = [
        "continue",
        "resume",
        "keep going",
        "finish",
        "complete",
        "이어",
        "이어쓰기",
        "계속",
        "마저",
        "완성",
        "끝까지",
    ]
    return (
        any(keyword in request for keyword in continue_keywords)
        or active_project_dir.name.lower() in request
        or (title and title.casefold() in request)
    )


def _apply_auto_brief(state: dict[str, Any], ceo_request: str) -> None:
    target_pages = _infer_target_pages(ceo_request)
    existing_total = state.get("total_chapters")
    if target_pages is None and existing_total and not _has_scale_signal(ceo_request):
        target_chapters = int(existing_total)
    else:
        target_chapters = _infer_target_chapters(ceo_request, target_pages)
    state["automation_mode"] = "full_auto"
    state["ceo_initial_request"] = ceo_request
    state["target_pages"] = target_pages
    state["auto_target_chapters"] = target_chapters
    state["total_chapters"] = target_chapters
    state["current_chapter"] = max(1, int(state.get("current_chapter") or 1))


def _auto_request_for_step(state: dict[str, Any], ceo_request: str) -> str:
    target_pages = state.get("target_pages") or "미정"
    target_chapters = state.get("auto_target_chapters") or state.get("total_chapters") or "미정"
    return f"""[완전자동화 모드]
CEO 최초 명령:
{ceo_request}

자동 운영 지침:
- 사용자는 이후 단계별 지시를 하지 않는다. 각 역할은 이전 산출물과 Next Handoff를 읽고 스스로 다음 역할이 일할 수 있게 결과물을 완성한다.
- 목표 분량: {target_pages}p
- 목표 장 수: {target_chapters}장
- 짧은 단편/1챕터 요청이면 1장 완결 구조로 만든다.
- 장편 요청이면 목차에서 전체 장 수와 장별 기능을 확정하고, 각 챕터의 마지막에 다음 챕터 작업 메모를 남긴다.
- 현재 챕터만 작성하되, 전체 원고가 끝까지 자동 진행될 수 있도록 파일 경로와 미해결 사항을 명확히 적는다.
"""


def _infer_title(ceo_request: str) -> str:
    for pattern in [r"제목\s*[:：]\s*([^\n,]+)", r"[『《<\"]([^『』《》<>\"]+)[』》>\"]"]:
        match = re.search(pattern, ceo_request)
        if match:
            return match.group(1).strip()[:40]
    compact = re.sub(r"\s+", " ", ceo_request).strip()
    return compact[:24] or "자동 프로젝트"


def _infer_genre(ceo_request: str) -> str:
    candidates = [
        "스릴러",
        "판타지",
        "로맨스",
        "미스터리",
        "추리",
        "SF",
        "공포",
        "무협",
        "현대문학",
        "단편",
        "장편",
    ]
    for candidate in candidates:
        if candidate.lower() in ceo_request.lower():
            return candidate
    return "미정"


def _infer_target_pages(ceo_request: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:p|P|페이지|쪽)", ceo_request)
    if not match:
        return None
    return int(match.group(1))


def _infer_target_chapters(ceo_request: str, target_pages: int | None) -> int:
    request = ceo_request.lower()
    if re.search(r"1\s*챕터|한\s*챕터|1\s*장만", ceo_request):
        return 1
    if "단편" in ceo_request:
        return 1
    if target_pages is not None:
        if target_pages <= 20:
            return 1
        return max(2, round(target_pages / 25))
    if "장편" in ceo_request:
        return 12
    if "중편" in ceo_request:
        return 4
    if "short" in request:
        return 1
    if "novel" in request:
        return 12
    return 1


def _has_scale_signal(ceo_request: str) -> bool:
    return bool(
        re.search(r"\d+\s*(?:p|P|페이지|쪽|챕터|장)", ceo_request)
        or any(keyword in ceo_request for keyword in ["단편", "중편", "장편", "한 챕터"])
    )


def _failed(project_dir: Path, completed_steps: list[str], message: str) -> AutoRunSummary:
    return AutoRunSummary(
        success=False,
        project_dir=project_dir,
        final_output=None,
        message=message,
        completed_steps=completed_steps,
    )


def _missing_setup_menus(project_dir: Path) -> list[str]:
    menus: list[str] = []
    if not _usable_file(project_dir / "story_bible.md"):
        menus.append("2")
    if not _usable_file(project_dir / "outline.md"):
        menus.append("3")
    return menus


def _usable_file(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="replace").strip())
