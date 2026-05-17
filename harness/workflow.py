from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowAction:
    menu: str
    label: str
    role: str
    prompt_file: str
    goal: str
    output_path: Path
    phase: str
    next_menu: str


ACTIONS = {
    "2": WorkflowAction(
        menu="2",
        label="기획 생성",
        role="planner",
        prompt_file="planner.md",
        goal="책의 장르, 콘셉트, 독자층, 주요 인물, 세계관, 문체 원칙을 정리한다.",
        output_path=Path("projects/book_001/story_bible.md"),
        phase="planned",
        next_menu="3. 목차 생성",
    ),
    "3": WorkflowAction(
        menu="3",
        label="목차 생성",
        role="outliner",
        prompt_file="outliner.md",
        goal="story_bible.md를 바탕으로 전체 목차, 총 장 수, 장별 사건 구조를 만든다.",
        output_path=Path("projects/book_001/outline.md"),
        phase="outlined",
        next_menu="4. 챕터 초안 생성",
    ),
    "4": WorkflowAction(
        menu="4",
        label="챕터 초안 생성",
        role="writer",
        prompt_file="writer.md",
        goal="story_bible.md와 outline.md를 바탕으로 현재 챕터 초안을 작성한다.",
        output_path=Path("projects/book_001/chapters/ch001_draft.md"),
        phase="drafted",
        next_menu="5. 편집본 생성",
    ),
    "5": WorkflowAction(
        menu="5",
        label="편집본 생성",
        role="editor",
        prompt_file="editor.md",
        goal="현재 챕터 초안을 더 읽기 좋고 일관된 편집본으로 고친다.",
        output_path=Path("projects/book_001/chapters/ch001_edited.md"),
        phase="edited",
        next_menu="6. 설정 검수",
    ),
    "6": WorkflowAction(
        menu="6",
        label="설정 검수",
        role="continuity_checker",
        prompt_file="continuity_checker.md",
        goal="현재 챕터 편집본의 설정, 시간선, 인물관계, 금지사항 위반을 점검한다.",
        output_path=Path("projects/book_001/reviews/ch001_continuity.md"),
        phase="checked",
        next_menu="7. 최종본 생성",
    ),
    "7": WorkflowAction(
        menu="7",
        label="최종본 생성",
        role="finalizer",
        prompt_file="finalizer.md",
        goal="검수 리포트를 반영해 현재 챕터 최종본을 만들고 다음 챕터 진행 준비를 남긴다.",
        output_path=Path("projects/book_001/chapters/ch001_final.md"),
        phase="finalized",
        next_menu="8. 현재 상태 보기",
    ),
}


def get_action(menu: str) -> WorkflowAction:
    try:
        return ACTIONS[menu]
    except KeyError as exc:
        raise ValueError(f"Unknown workflow menu: {menu}") from exc


def next_recommendation(phase: str) -> str:
    order = [
        ("created", "2. 기획 생성"),
        ("planned", "3. 목차 생성"),
        ("outlined", "4. 챕터 초안 생성"),
        ("drafted", "5. 편집본 생성"),
        ("edited", "6. 설정 검수"),
        ("checked", "7. 최종본 생성"),
        ("finalized", "8. 현재 상태 보기"),
    ]
    for current_phase, recommendation in order:
        if phase == current_phase:
            return recommendation
    return "2. 기획 생성"


def next_recommendation_for_state(state: dict) -> str:
    phase = state.get("phase", "created")
    if phase == "packaged":
        return "완전자동화 완료. 최종 원고 검토 필요"
    current = int(state.get("current_chapter") or 1)
    total = state.get("total_chapters")
    if phase == "finalized":
        completed = {int(chapter) for chapter in state.get("completed_chapters", [])}
        if total is not None and len(completed) >= int(total):
            return "전체 챕터 최종본 완료. 통합본/출간 패키지 생성 필요"
        if total is None or current <= int(total):
            return f"4. 챕터 초안 생성 ({current}장)"
        return "전체 챕터 최종본 완료. 통합본/출간 패키지 생성 필요"
    recommendation = next_recommendation(phase)
    if phase in {"outlined", "drafted", "edited", "checked"}:
        return f"{recommendation} ({current}장)"
    return recommendation
