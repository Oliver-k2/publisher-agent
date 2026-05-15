from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResultCheck:
    success: bool
    path: Path
    message: str


def check_result(expected_output: Path, *, newer_than: float | None = None) -> ResultCheck:
    if expected_output.exists() and expected_output.is_file():
        content = expected_output.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return ResultCheck(False, expected_output, f"empty: {expected_output}")
        if newer_than is not None and expected_output.stat().st_mtime < newer_than:
            return ResultCheck(False, expected_output, f"stale: {expected_output}")
        return ResultCheck(True, expected_output, f"found: {expected_output}")
    return ResultCheck(False, expected_output, f"not found: {expected_output}")


def create_correction_task(*, root: Path, original_task: Path, missing_output: Path) -> Path:
    correction_file = root / "tasks" / "correction_task.md"
    correction_file.parent.mkdir(parents=True, exist_ok=True)
    correction_file.write_text(
        f"""# 재시도 작업지시서

이전 작업이 완료 조건을 만족하지 못했습니다.

## 문제
- 누락된 출력 파일: {missing_output.as_posix()}
- 원래 작업지시서: {original_task.as_posix()}

## 목표
원래 작업지시서를 다시 읽고 누락된 출력 파일을 반드시 생성한다.

## 완료 조건
- `{missing_output.as_posix()}` 파일이 존재한다.
""",
        encoding="utf-8",
    )
    return correction_file
