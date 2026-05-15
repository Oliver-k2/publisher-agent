import json
from datetime import datetime, timezone
from pathlib import Path


def append_run_log(
    *,
    log_file: Path,
    role: str,
    menu: str,
    task_file: Path,
    expected_output: Path,
    success: bool,
    mode: str,
    message: str,
) -> dict[str, object]:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "menu": menu,
        "task_file": str(task_file),
        "expected_output": str(expected_output),
        "success": success,
        "mode": mode,
        "message": message,
    }
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
