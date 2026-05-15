import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodexRunResult:
    success: bool
    mode: str
    message: str
    returncode: int
    expected_output: Path


def run_codex(
    *,
    root: Path,
    task_file: Path,
    expected_output: Path,
    role: str,
    mode: str = "dummy",
) -> CodexRunResult:
    if mode == "dummy":
        return _run_dummy(task_file=task_file, expected_output=expected_output, role=role)
    if mode == "live":
        return _run_live(root=root, task_file=task_file, expected_output=expected_output)
    raise ValueError(f"Unknown Codex runner mode: {mode}")


def _run_dummy(*, task_file: Path, expected_output: Path, role: str) -> CodexRunResult:
    expected_output.parent.mkdir(parents=True, exist_ok=True)
    task_excerpt = task_file.read_text(encoding="utf-8")[:1200] if task_file.exists() else ""
    expected_output.write_text(
        f"""# Dummy result: {role}

이 파일은 하네스 MVP의 안전한 dummy 모드가 만든 샘플 산출물입니다.
실제 원고 품질을 판단하기 위한 결과가 아니라, 작업지시서 생성과 결과 회수 흐름을 검증하기 위한 파일입니다.

## 사용한 작업지시서 일부

```text
{task_excerpt}
```

## 다음 작업 메모
live 모드로 전환하면 Codex OAuth 세션이 같은 작업지시서를 읽고 이 파일을 실제 산출물로 갱신합니다.
""",
        encoding="utf-8",
    )
    return CodexRunResult(
        success=True,
        mode="dummy",
        message=f"Dummy output written to {expected_output}",
        returncode=0,
        expected_output=expected_output,
    )


def _run_live(*, root: Path, task_file: Path, expected_output: Path) -> CodexRunResult:
    codex_executable = _resolve_codex_executable()
    if codex_executable is None:
        return CodexRunResult(
            success=False,
            mode="live",
            message=(
                "Codex executable was not found. Run `codex --version` in the same terminal, "
                "or set CODEX_COMMAND to the full codex.exe path. On this machine it is often "
                "`C:\\Users\\user\\AppData\\Local\\OpenAI\\Codex\\bin\\codex.exe`."
            ),
            returncode=127,
            expected_output=expected_output,
        )

    task_prompt = (
        f"Read the task file at {task_file} and complete it exactly. "
        f"Write the required result to {expected_output}."
    )
    command = [
        str(codex_executable),
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(root),
        task_prompt,
    ]
    output_lines: list[str] = []
    try:
        process = subprocess.Popen(
            command,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        if process.stdout is not None:
            for line in process.stdout:
                _write_console(line)
                output_lines.append(line)
        returncode = process.wait()
    except FileNotFoundError as exc:
        return CodexRunResult(
            success=False,
            mode="live",
            message=f"Codex executable could not be launched: {exc}",
            returncode=127,
            expected_output=expected_output,
        )
    except OSError as exc:
        return CodexRunResult(
            success=False,
            mode="live",
            message=f"Codex executable could not be launched: {exc}",
            returncode=1,
            expected_output=expected_output,
        )
    output = "".join(output_lines).strip()
    return CodexRunResult(
        success=returncode == 0,
        mode="live",
        message=output or f"codex exec exited with {returncode}",
        returncode=returncode,
        expected_output=expected_output,
    )


def _write_console(text: str) -> None:
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        encoded = text.encode(encoding, errors="replace")
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write(encoded)
            buffer.flush()
            return
        sys.stdout.write(encoded.decode(encoding, errors="replace"))
        sys.stdout.flush()


def _resolve_codex_executable() -> Path | None:
    configured = os.environ.get("CODEX_COMMAND")
    if configured:
        configured_path = Path(configured)
        if configured_path.exists():
            return configured_path

    discovered = shutil.which("codex")
    if discovered:
        return Path(discovered)

    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe")
    candidates.append(Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "codex.exe")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
