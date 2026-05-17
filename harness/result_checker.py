from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ResultCheck:
    success: bool
    path: Path
    message: str


def check_result(
    expected_output: Path,
    *,
    newer_than: float | None = None,
    role: str | None = None,
    min_chars: int | None = None,
) -> ResultCheck:
    if expected_output.exists() and expected_output.is_file():
        content = expected_output.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return ResultCheck(False, expected_output, f"empty: {expected_output}")
        if newer_than is not None and expected_output.stat().st_mtime < newer_than:
            return ResultCheck(False, expected_output, f"stale: {expected_output}")
        if min_chars is not None and len(content.strip()) < min_chars:
            return ResultCheck(False, expected_output, f"too short: {expected_output}")
        missing_markers = _missing_required_markers(content, expected_output, role)
        if missing_markers:
            return ResultCheck(
                False,
                expected_output,
                f"incomplete: {expected_output}; missing markers: {', '.join(missing_markers)}",
            )
        return ResultCheck(True, expected_output, f"found: {expected_output}")
    return ResultCheck(False, expected_output, f"not found: {expected_output}")


def final_chapter_is_ready(path: Path) -> bool:
    """Return True only when a finalizer output is usable as manuscript canon."""
    if not path.exists() or not path.is_file():
        return False
    content = path.read_text(encoding="utf-8", errors="replace")
    status = _metadata_value(content, "final_status")
    if status is None:
        return False
    return status.upper() in {"READY", "READY_WITH_NOTES"}


def continuity_allows_finalizer(path: Path) -> bool:
    """Return True when a continuity report explicitly permits finalization."""
    if not path.exists() or not path.is_file():
        return False
    content = path.read_text(encoding="utf-8", errors="replace")
    status = _metadata_value(content, "status")
    gate = _metadata_value(content, "proceed_to_finalizer")
    if status and status.upper() == "FAIL":
        return False
    if gate and gate.lower() == "no":
        return False
    if gate and gate.lower() == "yes":
        return _section_is_empty_or_none(content, "Blockers")
    return False


def create_correction_task(*, root: Path, original_task: Path, missing_output: Path) -> Path:
    correction_file = root / "tasks" / "correction_task.md"
    correction_file.parent.mkdir(parents=True, exist_ok=True)
    correction_file.write_text(
        f"""# 재시도 작업지시서

이전 작업이 완료 조건을 만족하지 못했습니다.

## 문제
- 누락되었거나 불완전한 출력 파일: {missing_output.as_posix()}
- 원래 작업지시서: {original_task.as_posix()}

## 목표
원래 작업지시서를 다시 읽고 출력 파일을 완전한 형태로 다시 생성한다.

## 완료 조건
- `{missing_output.as_posix()}` 파일이 존재한다.
- 역할별 필수 섹션과 `Next Handoff`, `다음 작업 메모`가 포함되어 있다.
""",
        encoding="utf-8",
    )
    return correction_file


def _metadata_value(content: str, key: str) -> str | None:
    pattern = re.compile(rf"^\s*-\s*{re.escape(key)}\s*:\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(content)
    if not match:
        return None
    return match.group(1).strip().strip("`")


def _section_is_empty_or_none(content: str, heading: str) -> bool:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(content)
    if not match:
        return False
    body = match.group(1).strip()
    if not body:
        return True
    normalized = re.sub(r"[\s\-.]", "", body)
    return normalized in {"없음", "해당없음", "none", "None", "NONE"}


def _missing_required_markers(content: str, expected_output: Path, role: str | None) -> list[str]:
    markers = required_markers_for(role, expected_output)
    if not markers:
        return []
    return [marker for marker in markers if marker not in content]


def required_markers_for(role: str | None, expected_output: Path) -> list[str]:
    name = expected_output.name
    path = expected_output.as_posix()
    resolved_role = role or _role_from_path(name, path)

    marker_sets = {
        "producer": ["# Production Handoff", "## Metadata", "## Task Packet", "## Next Handoff"],
        "planner": ["# Story Bible", "## Metadata", "## Core Concept", "## Next Handoff"],
        "outliner": ["# Outline", "## Metadata", "## Chapter Table", "## Next Handoff"],
        "writer": ["## Metadata", "## Draft Body", "## Draft Notes", "## Next Handoff"],
        "editor": ["## Metadata", "## Edited Body", "## Edit Report", "## Next Handoff"],
        "continuity_checker": [
            "## Metadata",
            "## Final Gate Recommendation",
            "## Next Handoff",
        ],
        "finalizer": ["## Metadata", "## Final Body", "## Finalization Report", "## Next Handoff"],
        "packager": ["# Manuscript Package", "## Metadata", "## Manuscript", "## Package Report"],
    }
    markers = marker_sets.get(resolved_role, [])
    if expected_output.suffix == ".md":
        markers = [*markers, "## 다음 작업 메모"]
    return list(dict.fromkeys(markers))


def _role_from_path(name: str, path: str) -> str | None:
    if name == "production_plan.md":
        return "producer"
    if name == "story_bible.md":
        return "planner"
    if name == "outline.md":
        return "outliner"
    if name.endswith("_draft.md"):
        return "writer"
    if name.endswith("_edited.md"):
        return "editor"
    if name.endswith("_continuity.md"):
        return "continuity_checker"
    if name.endswith("_final.md"):
        return "finalizer"
    if path.endswith("/final/book_final.md"):
        return "packager"
    return None
