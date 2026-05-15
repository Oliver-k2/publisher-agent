import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.codex_runner import _write_console, run_codex
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
)
from harness.task_builder import build_task
from harness.workflow import get_action


class HarnessMvpTests(unittest.TestCase):
    def test_ensure_project_creates_default_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "projects" / "book_001"

            state = ensure_project(
                project_dir,
                title="Test Novel",
                genre="Mystery",
            )

            project_file = project_dir / "project.json"
            self.assertTrue(project_file.exists())
            self.assertEqual(state["project_id"], "book_001")
            self.assertEqual(state["title"], "Test Novel")
            self.assertEqual(state["genre"], "Mystery")
            self.assertEqual(state["phase"], "created")
            self.assertEqual(state["current_chapter"], 1)
            self.assertEqual(state["artifacts"], {})
            self.assertEqual(state["decisions"], [])
            self.assertEqual(state["runs"], [])
            self.assertEqual(load_project(project_dir), state)


    def test_create_project_uses_next_book_id_and_lists_projects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir) / "projects"
            ensure_project(projects_dir / "book_001", title="First", genre="Thriller")

            project_dir, state = create_project(projects_dir, title="Second", genre="SF")

            self.assertEqual(project_dir, projects_dir / "book_002")
            self.assertEqual(state["project_id"], "book_002")
            self.assertEqual(state["title"], "Second")
            self.assertEqual(list_projects(projects_dir), ["book_001", "book_002"])

    def test_active_project_selection_persists_between_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir) / "projects"
            ensure_project(projects_dir / "book_001", title="First", genre="Thriller")
            ensure_project(projects_dir / "book_002", title="Second", genre="SF")

            save_active_project_id(projects_dir, "book_002")

            self.assertEqual(get_active_project_dir(projects_dir), projects_dir / "book_002")


    def test_save_project_preserves_utf8_and_json_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "projects" / "book_001"
            state = ensure_project(project_dir, title="달빛 회사", genre="판타지")
            state["decisions"].append({"note": "주인공은 편집자다"})

            save_project(project_dir, state)

            raw = (project_dir / "project.json").read_text(encoding="utf-8")
            self.assertIn("달빛 회사", raw)
            self.assertEqual(load_project(project_dir)["decisions"][0]["note"], "주인공은 편집자다")

    def test_load_project_accepts_utf8_bom_json_written_by_windows_tools(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "projects" / "book_001"
            project_dir.mkdir(parents=True)
            (project_dir / "project.json").write_text(
                json.dumps(
                    {
                        "project_id": "book_001",
                        "title": "Bom Book",
                        "genre": "Thriller",
                        "phase": "created",
                        "current_chapter": 1,
                        "mode": "dummy",
                        "artifacts": {},
                        "decisions": [],
                        "runs": [],
                    }
                ),
                encoding="utf-8-sig",
            )

            state = load_project(project_dir)

            self.assertEqual(state["title"], "Bom Book")


    def test_build_task_writes_required_sections_and_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_001"
            state = ensure_project(project_dir, title="Orbit", genre="SF")
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "planner.md").write_text("You are the planner.", encoding="utf-8")

            task = build_task(
                root=root,
                project_dir=project_dir,
                action=get_action("2"),
                state=state,
                user_request="quiet literary SF",
            )

            task_text = task.task_file.read_text(encoding="utf-8")
            self.assertEqual(task.task_file, root / "tasks" / "current_task.md")
            self.assertEqual(task.expected_output, root / "projects" / "book_001" / "story_bible.md")
            for section in ["목표", "입력 파일", "출력 파일", "금지사항", "완료 조건"]:
                self.assertIn(f"## {section}", task_text)
            self.assertIn("prompts/planner.md", task_text)
            self.assertIn("projects/book_001/story_bible.md", task_text)
            self.assertIn("quiet literary SF", task_text)

    def test_build_task_uses_selected_project_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_002"
            state = ensure_project(project_dir, title="Second", genre="SF", project_id="book_002")
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "outliner.md").write_text("You are the outliner.", encoding="utf-8")

            task = build_task(
                root=root,
                project_dir=project_dir,
                action=get_action("3"),
                state=state,
                user_request="",
            )

            task_text = task.task_file.read_text(encoding="utf-8")
            self.assertEqual(task.expected_output, root / "projects" / "book_002" / "outline.md")
            self.assertIn("projects/book_002/story_bible.md", task_text)
            self.assertIn("projects/book_002/outline.md", task_text)

    def test_build_task_uses_safe_fence_when_prompt_contains_code_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_001"
            state = ensure_project(project_dir, title="Orbit", genre="SF")
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "planner.md").write_text(
                "Planner rules\n\n```md\n# Required Shape\n```\n",
                encoding="utf-8",
            )

            task = build_task(
                root=root,
                project_dir=project_dir,
                action=get_action("2"),
                state=state,
                user_request="",
            )

            task_text = task.task_file.read_text(encoding="utf-8")
            self.assertIn("````text\nPlanner rules\n\n```md\n# Required Shape\n```\n````", task_text)


    def test_dummy_runner_creates_expected_output_and_result_checker_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "tasks" / "current_task.md"
            expected_output = root / "projects" / "book_001" / "outline.md"
            task_file.parent.mkdir(parents=True)
            task_file.write_text("## 목표\n목차 생성\n", encoding="utf-8")

            run = run_codex(
                root=root,
                task_file=task_file,
                expected_output=expected_output,
                role="outliner",
                mode="dummy",
            )
            check = check_result(expected_output)

            self.assertTrue(run.success)
            self.assertEqual(run.mode, "dummy")
            self.assertTrue(expected_output.exists())
            self.assertIn("# Dummy result: outliner", expected_output.read_text(encoding="utf-8"))
            self.assertTrue(check.success)
            self.assertEqual(check.path, expected_output)

    def test_live_runner_reports_missing_codex_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "tasks" / "current_task.md"
            expected_output = root / "projects" / "book_001" / "story_bible.md"
            task_file.parent.mkdir(parents=True)
            task_file.write_text("## Mission\nPlan the book.\n", encoding="utf-8")

            with patch("harness.codex_runner._resolve_codex_executable", return_value=None):
                run = run_codex(
                    root=root,
                    task_file=task_file,
                    expected_output=expected_output,
                    role="planner",
                    mode="live",
                )

            self.assertFalse(run.success)
            self.assertEqual(run.returncode, 127)
            self.assertIn("Codex executable was not found", run.message)
            self.assertFalse(expected_output.exists())

    def test_live_runner_streams_codex_output_while_collecting_message(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = ["planning...\n", "done\n"]
                self.returncode = 0

            def wait(self):
                return self.returncode

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "tasks" / "current_task.md"
            expected_output = root / "projects" / "book_001" / "story_bible.md"
            task_file.parent.mkdir(parents=True)
            task_file.write_text("## Mission\nPlan the book.\n", encoding="utf-8")

            fake_process = FakeProcess()
            with patch("harness.codex_runner._resolve_codex_executable", return_value=Path("codex")):
                with patch("harness.codex_runner.subprocess.Popen", return_value=fake_process) as popen:
                    with patch("harness.codex_runner._write_console") as streamed:
                        run = run_codex(
                            root=root,
                            task_file=task_file,
                            expected_output=expected_output,
                            role="planner",
                            mode="live",
                        )

            self.assertTrue(run.success)
            self.assertEqual(run.returncode, 0)
            self.assertIn("planning...", run.message)
            self.assertIn("done", run.message)
            streamed.assert_any_call("planning...\n")
            streamed.assert_any_call("done\n")
            popen.assert_called_once()
            self.assertEqual(popen.call_args.kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.STDOUT)
            self.assertEqual(popen.call_args.kwargs["encoding"], "utf-8")
            self.assertEqual(popen.call_args.kwargs["errors"], "replace")

    def test_write_console_falls_back_when_terminal_encoding_cannot_write_text(self):
        class FakeBuffer:
            def __init__(self):
                self.data = b""
                self.flushed = False

            def write(self, data):
                self.data += data

            def flush(self):
                self.flushed = True

        class Cp949Console:
            encoding = "cp949"

            def __init__(self):
                self.buffer = FakeBuffer()

            def write(self, text):
                text.encode(self.encoding)

            def flush(self):
                pass

        console = Cp949Console()

        with patch("harness.codex_runner.sys.stdout", console):
            _write_console("status — running\n")

        self.assertIn(b"status ? running", console.buffer.data)
        self.assertTrue(console.buffer.flushed)

    def test_live_runner_reports_launch_os_errors_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "tasks" / "current_task.md"
            expected_output = root / "projects" / "book_001" / "story_bible.md"
            task_file.parent.mkdir(parents=True)
            task_file.write_text("## Mission\nPlan the book.\n", encoding="utf-8")

            with patch("harness.codex_runner._resolve_codex_executable", return_value=Path("codex")):
                with patch("harness.codex_runner.subprocess.Popen", side_effect=OSError("permission denied")):
                    run = run_codex(
                        root=root,
                        task_file=task_file,
                        expected_output=expected_output,
                        role="planner",
                        mode="live",
                    )

            self.assertFalse(run.success)
            self.assertEqual(run.returncode, 1)
            self.assertIn("permission denied", run.message)


    def test_result_checker_reports_missing_output_and_builds_correction_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing_output = root / "projects" / "book_001" / "missing.md"
            check = check_result(missing_output)

            correction = create_correction_task(
                root=root,
                original_task=root / "tasks" / "current_task.md",
                missing_output=missing_output,
            )

            self.assertFalse(check.success)
            self.assertIn("not found", check.message)
            self.assertTrue(correction.exists())
            self.assertIn("missing.md", correction.read_text(encoding="utf-8"))

    def test_result_checker_rejects_empty_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "projects" / "book_001" / "story_bible.md"
            output.parent.mkdir(parents=True)
            output.write_text(" \n\t\n", encoding="utf-8")

            check = check_result(output)

            self.assertFalse(check.success)
            self.assertIn("empty", check.message)

    def test_result_checker_rejects_output_older_than_current_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "projects" / "book_001" / "story_bible.md"
            output.parent.mkdir(parents=True)
            output.write_text("old result", encoding="utf-8")
            newer_than = output.stat().st_mtime + 10

            check = check_result(output, newer_than=newer_than)

            self.assertFalse(check.success)
            self.assertIn("stale", check.message)


    def test_logger_appends_jsonl_run_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_file = root / "logs" / "runs.jsonl"

            append_run_log(
                log_file=log_file,
                role="writer",
                menu="4",
                task_file=root / "tasks" / "current_task.md",
                expected_output=root / "projects" / "book_001" / "chapters" / "ch001_draft.md",
                success=True,
                mode="dummy",
                message="ok",
            )

            lines = log_file.read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            self.assertEqual(record["role"], "writer")
            self.assertEqual(record["menu"], "4")
            self.assertTrue(record["expected_output"].endswith("ch001_draft.md"))
            self.assertTrue(record["success"])
            self.assertEqual(record["mode"], "dummy")
            self.assertIn("timestamp", record)


if __name__ == "__main__":
    unittest.main()
