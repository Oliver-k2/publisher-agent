from pathlib import Path

from harness.codex_runner import run_codex
from harness.logger import append_run_log
from harness.result_checker import check_result, create_correction_task
from harness.state_manager import ensure_project, load_project, save_project, update_after_run
from harness.task_builder import build_task
from harness.workflow import get_action, next_recommendation


ROOT = Path(__file__).resolve().parent
PROJECT_DIR = ROOT / "projects" / "book_001"
LOG_FILE = ROOT / "logs" / "runs.jsonl"


def main() -> None:
    bootstrap_workspace()
    print("\nAI 글쓰기 회사 하네스 MVP")
    print("사용자는 CEO, Codex는 작업 직원, 하네스는 운영 시스템입니다.")

    while True:
        state = ensure_project(PROJECT_DIR)
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
        if choice in {"2", "3", "4", "5", "6", "7"}:
            run_workflow(choice)
            continue

        print("알 수 없는 메뉴입니다.")


def bootstrap_workspace() -> None:
    for path in [
        ROOT / "harness",
        ROOT / "prompts",
        ROOT / "tasks" / "history",
        ROOT / "projects" / "book_001" / "chapters",
        ROOT / "projects" / "book_001" / "reviews",
        ROOT / "projects" / "book_001" / "summaries",
        ROOT / "projects" / "book_001" / "final",
        ROOT / "logs",
        ROOT / "templates",
        ROOT / "future_crewai",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    ensure_project(PROJECT_DIR)


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
    print("0. 종료")
    print(f"현재 책: {state.get('title')} / 장르: {state.get('genre')} / 단계: {state.get('phase')}")
    print(f"실행 모드: {state.get('mode', 'dummy')}")
    print(f"추천 다음 단계: {next_recommendation(state.get('phase', 'created'))}")


def create_new_book() -> None:
    title = input("책 제목: ").strip() or "Untitled Book"
    genre = input("장르: ").strip() or "미정"
    state = ensure_project(PROJECT_DIR, title=title, genre=genre)
    state["title"] = title
    state["genre"] = genre
    state["phase"] = "created"
    state["current_chapter"] = 1
    state["artifacts"] = {}
    state["decisions"] = []
    state["runs"] = []
    save_project(PROJECT_DIR, state)
    print(f"새 책 프로젝트를 준비했습니다: {title}")


def run_workflow(choice: str) -> None:
    state = load_project(PROJECT_DIR)
    action = get_action(choice)
    user_request = input("CEO 추가 요청(없으면 Enter): ").strip()
    built_task = build_task(root=ROOT, action=action, state=state, user_request=user_request)
    mode = state.get("mode", "dummy")

    run = run_codex(
        root=ROOT,
        task_file=built_task.task_file,
        expected_output=built_task.expected_output,
        role=built_task.role,
        mode=mode,
    )
    check = check_result(built_task.expected_output)
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
        update_after_run(
            PROJECT_DIR,
            state,
            phase=action.phase,
            artifact_key=action.role,
            artifact_path=built_task.expected_output.relative_to(ROOT),
            run_record=record,
        )
        print(f"작업 완료: {built_task.label}")
        print(f"작업지시서: {built_task.task_file}")
        print(f"결과 파일: {built_task.expected_output}")
        print(f"다음 추천: {action.next_menu}")
        return

    correction = create_correction_task(
        root=ROOT,
        original_task=built_task.task_file,
        missing_output=built_task.expected_output,
    )
    print("작업이 완료 조건을 만족하지 못했습니다.")
    print(f"재시도 작업지시서: {correction}")


def show_status() -> None:
    state = load_project(PROJECT_DIR)
    print("\n--- 현재 상태 ---")
    print(f"project_id: {state.get('project_id')}")
    print(f"title: {state.get('title')}")
    print(f"genre: {state.get('genre')}")
    print(f"phase: {state.get('phase')}")
    print(f"current_chapter: {state.get('current_chapter')}")
    print(f"mode: {state.get('mode', 'dummy')}")
    print("artifacts:")
    for key, value in state.get("artifacts", {}).items():
        print(f"- {key}: {value}")
    print(f"runs: {len(state.get('runs', []))}")


def toggle_mode() -> None:
    state = load_project(PROJECT_DIR)
    current = state.get("mode", "dummy")
    state["mode"] = "live" if current == "dummy" else "dummy"
    save_project(PROJECT_DIR, state)
    print(f"실행 모드가 {state['mode']}로 변경되었습니다.")


if __name__ == "__main__":
    main()
