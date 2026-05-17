from pathlib import Path

from harness.automation import run_full_automation
from harness.codex_runner import run_codex
from harness.logger import append_run_log
from harness.result_checker import check_result, create_correction_task
from harness.state_manager import (
    create_project,
    ensure_project,
    get_active_project_dir,
    list_projects,
    load_project,
    save_active_project_id,
    save_project,
    update_after_run,
    write_project_status,
)
from harness.task_builder import build_task
from harness.workflow import get_action, next_recommendation_for_state


ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = ROOT / "projects"
LOG_FILE = ROOT / "logs" / "runs.jsonl"


def main() -> None:
    bootstrap_workspace()
    print("\nAI 글쓰기 회사 하네스 MVP")
    print("사용자는 CEO, Codex는 작업 직원, 하네스는 운영 시스템입니다.")

    while True:
        project_dir = get_current_project_dir()
        state = ensure_project(project_dir)
        print_menu(state)
        choice = input("메뉴 선택: ").strip()

        if choice == "0":
            print("종료합니다.")
            return
        if choice == "1":
            create_new_book()
            continue
        if choice == "8":
            show_status()
            continue
        if choice == "9":
            toggle_mode()
            continue
        if choice == "10":
            select_book()
            continue
        if choice == "11":
            run_auto_mode()
            continue
        if choice in {"2", "3", "4", "5", "6", "7"}:
            run_workflow(choice)
            continue

        print("알 수 없는 메뉴입니다.")


def bootstrap_workspace() -> None:
    for path in [
        ROOT / "harness",
        ROOT / "prompts",
        ROOT / "tasks" / "history",
        PROJECTS_DIR,
        ROOT / "logs",
        ROOT / "templates",
        ROOT / "future_crewai",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    ensure_project(get_current_project_dir())


def get_current_project_dir() -> Path:
    return get_active_project_dir(PROJECTS_DIR)


def print_menu(state: dict) -> None:
    print("\n--- 메뉴 ---")
    print("1. 새 책 만들기")
    print("2. 기획 생성")
    print("3. 목차 생성")
    print("4. 챕터 초안 생성")
    print("5. 편집본 생성")
    print("6. 설정 검수")
    print("7. 최종본 생성")
    print("8. 현재 상태 보기")
    print("9. 실행 모드 변경: dummy / live")
    print("10. 책 선택")
    print("11. 완전자동화 모드")
    print("0. 종료")
    print(f"현재 책: {state.get('project_id')} - {state.get('title')} / 장르: {state.get('genre')} / 단계: {state.get('phase')}")
    print(f"챕터 진행: 현재 {state.get('current_chapter', 1)}장 / 총 {state.get('total_chapters') or '미정'}장")
    print(f"완료 챕터: {_format_completed_chapters(state)}")
    print(f"실행 모드: {state.get('mode', 'dummy')}")
    print(f"추천 다음 단계: {next_recommendation_for_state(state)}")


def create_new_book() -> None:
    title = input("책 제목: ").strip() or "Untitled Book"
    genre = input("장르: ").strip() or "미정"
    project_dir, state = create_project(PROJECTS_DIR, title=title, genre=genre)
    save_active_project_id(PROJECTS_DIR, state["project_id"])
    print(f"새 책 프로젝트를 준비하고 선택했습니다: {state['project_id']} - {title}")


def run_workflow(choice: str) -> None:
    project_dir = get_current_project_dir()
    state = load_project(project_dir)
    action = get_action(choice)
    user_request = input("CEO 추가 요청(없으면 Enter): ").strip()
    built_task = build_task(
        root=ROOT,
        project_dir=project_dir,
        action=action,
        state=state,
        user_request=user_request,
    )
    mode = state.get("mode", "dummy")

    run = run_codex(
        root=ROOT,
        task_file=built_task.task_file,
        expected_output=built_task.expected_output,
        role=built_task.role,
        mode=mode,
    )
    check = check_result(
        built_task.expected_output,
        newer_than=built_task.task_file.stat().st_mtime,
        role=built_task.role,
    )
    success = run.success and check.success
    message = run.message if success else f"{run.message}; {check.message}"
    record = append_run_log(
        log_file=LOG_FILE,
        role=built_task.role,
        menu=built_task.menu,
        task_file=built_task.task_file,
        expected_output=built_task.expected_output,
        success=success,
        mode=mode,
        message=message,
    )

    if success:
        updated_state = update_after_run(
            project_dir,
            state,
            phase=action.phase,
            artifact_key=action.role,
            artifact_path=built_task.expected_output.relative_to(ROOT),
            run_record=record,
        )
        status_file = write_project_status(project_dir, updated_state)
        print(f"작업 완료: {built_task.label}")
        print(f"작업지시서: {built_task.task_file}")
        print(f"결과 파일: {built_task.expected_output}")
        print(f"상태 대시보드: {status_file}")
        print(f"다음 추천: {next_recommendation_for_state(updated_state)}")
        return

    correction = create_correction_task(
        root=ROOT,
        original_task=built_task.task_file,
        missing_output=built_task.expected_output,
    )
    print("작업이 완료 조건을 만족하지 못했습니다.")
    print(f"재시도 작업지시서: {correction}")


def show_status() -> None:
    state = load_project(get_current_project_dir())
    print("\n--- 현재 상태 ---")
    print(f"project_id: {state.get('project_id')}")
    print(f"title: {state.get('title')}")
    print(f"genre: {state.get('genre')}")
    print(f"phase: {state.get('phase')}")
    print(f"current_chapter: {state.get('current_chapter')}")
    print(f"total_chapters: {state.get('total_chapters') or '미정'}")
    print(f"completed_chapters: {_format_completed_chapters(state)}")
    print(f"mode: {state.get('mode', 'dummy')}")
    print("artifacts:")
    for key, value in state.get("artifacts", {}).items():
        print(f"- {key}: {value}")
    print("chapter_artifacts:")
    for chapter, artifacts in sorted(state.get("chapter_artifacts", {}).items()):
        print(f"- {chapter}:")
        for key, value in sorted(artifacts.items()):
            print(f"  - {key}: {value}")
    print(f"runs: {len(state.get('runs', []))}")
    print(f"추천 다음 단계: {next_recommendation_for_state(state)}")
    print(f"상태 대시보드: {write_project_status(get_current_project_dir(), state)}")


def toggle_mode() -> None:
    project_dir = get_current_project_dir()
    state = load_project(project_dir)
    current = state.get("mode", "dummy")
    state["mode"] = "live" if current == "dummy" else "dummy"
    save_project(project_dir, state)
    print(f"실행 모드가 {state['mode']}로 변경되었습니다.")


def select_book() -> None:
    project_ids = list_projects(PROJECTS_DIR)
    if not project_ids:
        print("선택할 책이 없습니다. 먼저 1번으로 새 책을 만들어 주세요.")
        return

    active_id = get_current_project_dir().name
    print("\n--- 책 목록 ---")
    for index, project_id in enumerate(project_ids, start=1):
        state = load_project(PROJECTS_DIR / project_id)
        marker = "*" if project_id == active_id else " "
        print(
            f"{index}. {marker} {project_id} - {state.get('title')} "
            f"/ 장르: {state.get('genre')} / 단계: {state.get('phase')}"
        )

    selected = input("선택할 책 번호(취소는 Enter): ").strip()
    if not selected:
        print("책 선택을 취소했습니다.")
        return
    if not selected.isdigit():
        print("숫자로 선택해 주세요.")
        return

    index = int(selected)
    if index < 1 or index > len(project_ids):
        print("목록에 없는 번호입니다.")
        return

    project_id = project_ids[index - 1]
    save_active_project_id(PROJECTS_DIR, project_id)
    state = load_project(PROJECTS_DIR / project_id)
    print(f"현재 책을 선택했습니다: {project_id} - {state.get('title')}")


def run_auto_mode() -> None:
    print("\n--- 완전자동화 모드 ---")
    print("CEO 최초 명령을 한 번만 입력하면 producer부터 최종 원고 패키징까지 순차 실행합니다.")
    print("예: 300p 분량의 심리 스릴러 장편소설을 써줘. 제목은 악마소녀.")
    ceo_request = input("CEO 최초 명령: ").strip()
    if not ceo_request:
        print("자동화를 취소했습니다. 최초 명령이 비어 있습니다.")
        return

    active_project_dir = get_current_project_dir()
    summary = run_full_automation(
        root=ROOT,
        projects_dir=PROJECTS_DIR,
        log_file=LOG_FILE,
        ceo_request=ceo_request,
        active_project_dir=active_project_dir,
    )
    print("\n--- 완전자동화 결과 ---")
    print(f"프로젝트: {summary.project_dir}")
    print(f"완료 단계 수: {len(summary.completed_steps)}")
    if summary.success:
        print(summary.message)
        print(f"최종 원고: {summary.final_output}")
        print(f"상태 대시보드: {summary.project_dir / 'project_status.md'}")
        return
    print("자동화가 중단되었습니다.")
    print(f"사유: {summary.message}")
    print(f"마지막까지 완료된 단계: {', '.join(summary.completed_steps) or '없음'}")


def _format_completed_chapters(state: dict) -> str:
    completed = state.get("completed_chapters", [])
    if not completed:
        return "없음"
    return ", ".join(f"{int(chapter)}장" for chapter in completed)


if __name__ == "__main__":
    main()
