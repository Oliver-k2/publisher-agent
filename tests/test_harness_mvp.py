import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.automation import (
    _infer_target_chapters,
    _infer_target_pages,
    _select_or_create_auto_project,
    _run_custom_step,
    run_full_automation,
)
from harness.codex_runner import CodexRunResult, _resolve_codex_executable, _write_console, run_codex
from harness.logger import append_run_log
from harness.result_checker import (
    check_result,
    continuity_allows_finalizer,
    create_correction_task,
    final_chapter_is_ready,
)
from harness.state_manager import (
    chapter_id,
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

    def test_build_task_uses_current_chapter_paths_and_previous_final(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_002"
            state = ensure_project(project_dir, title="Second", genre="SF", project_id="book_002")
            state["current_chapter"] = 2
            state["total_chapters"] = 12
            state["completed_chapters"] = [1]
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "writer.md").write_text("You are the writer.", encoding="utf-8")
            (project_dir / "chapters" / "ch001_final.md").write_text(
                "## Metadata\n- final_status: READY\n\n## Final Body\nchapter one\n",
                encoding="utf-8",
            )

            task = build_task(
                root=root,
                project_dir=project_dir,
                action=get_action("4"),
                state=state,
                user_request="",
            )

            task_text = task.task_file.read_text(encoding="utf-8")
            self.assertEqual(task.expected_output, root / "projects" / "book_002" / "chapters" / "ch002_draft.md")
            self.assertIn("current_chapter_id: ch002", task_text)
            self.assertIn("## 현재 챕터 할당", task_text)
            self.assertIn("projects/book_002/chapters/ch001_final.md", task_text)
            self.assertIn("projects/book_002/chapters/ch002_draft.md", task_text)

    def test_build_task_embeds_current_chapter_table_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_002"
            state = ensure_project(project_dir, title="Second", genre="SF", project_id="book_002")
            state["current_chapter"] = 3
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "writer.md").write_text("You are the writer.", encoding="utf-8")
            (project_dir / "outline.md").write_text(
                "| chapter | title | purpose | conflict | turn | ending_hook |\n"
                "|---|---|---|---|---|---|\n"
                "| 3 | 방송 나온 거지 | 악의가 일상에 들어온다 | 친구들이 조롱한다 | 감정을 연기한다 | 한 번만 더 울어줄 수 있니 |\n",
                encoding="utf-8",
            )

            task = build_task(
                root=root,
                project_dir=project_dir,
                action=get_action("4"),
                state=state,
                user_request="",
            )

            task_text = task.task_file.read_text(encoding="utf-8")
            self.assertIn("- chapter: 3", task_text)
            self.assertIn("- title: 방송 나온 거지", task_text)
            self.assertIn("- ending_hook: 한 번만 더 울어줄 수 있니", task_text)

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

    def test_finalizer_update_records_completed_chapter_and_advances_current(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_001"
            state = ensure_project(project_dir, title="Orbit", genre="SF")
            (project_dir / "outline.md").write_text(
                "| chapter | title |\n|---|---|\n| 1 | Start |\n| 2 | Next |\n",
                encoding="utf-8",
            )
            final_path = project_dir / "chapters" / "ch001_final.md"
            final_path.write_text(
                "# Chapter 1 Final\n\n"
                "## Metadata\n"
                "- project_id: book_001\n"
                "- chapter_id: ch001\n"
                "- final_status: READY\n\n"
                "## Final Body\n본문\n",
                encoding="utf-8",
            )

            updated = update_after_run(
                project_dir,
                state,
                phase="finalized",
                artifact_key="finalizer",
                artifact_path=Path("projects/book_001/chapters/ch001_final.md"),
                run_record={"success": True},
            )

            self.assertEqual(updated["total_chapters"], 2)
            self.assertEqual(updated["completed_chapters"], [1])
            self.assertEqual(updated["current_chapter"], 2)
            self.assertEqual(
                updated["chapter_artifacts"]["ch001"]["finalizer"],
                "projects/book_001/chapters/ch001_final.md",
            )

    def test_blocked_finalizer_output_does_not_complete_chapter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_001"
            state = ensure_project(project_dir, title="Orbit", genre="SF")
            (project_dir / "outline.md").write_text(
                "| chapter | title |\n|---|---|\n| 1 | Start |\n| 2 | Next |\n",
                encoding="utf-8",
            )
            final_path = project_dir / "chapters" / "ch001_final.md"
            final_path.write_text(
                "# Chapter 1 Final\n\n"
                "## Metadata\n"
                "- project_id: book_001\n"
                "- chapter_id: ch001\n"
                "- final_status: BLOCKED\n\n"
                "## Final Body\n보류\n",
                encoding="utf-8",
            )

            updated = update_after_run(
                project_dir,
                state,
                phase="finalized",
                artifact_key="finalizer",
                artifact_path=Path("projects/book_001/chapters/ch001_final.md"),
                run_record={"success": True},
            )
            reloaded = load_project(project_dir)
            status_file = write_project_status(project_dir, reloaded)
            status_text = status_file.read_text(encoding="utf-8")

            self.assertFalse(final_chapter_is_ready(final_path))
            self.assertEqual(updated["completed_chapters"], [])
            self.assertEqual(reloaded["completed_chapters"], [])
            self.assertIn("| ch001 | Start | current |", status_text)
            self.assertIn("| ch001 | Start | current | no | no | no | blocked |", status_text)

    def test_continuity_gate_requires_explicit_finalizer_permission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review = Path(temp_dir) / "ch001_continuity.md"
            review.write_text(
                "# Chapter 1 Continuity Report\n\n"
                "## Metadata\n"
                "- status: FAIL\n\n"
                "## Blockers\n"
                "- id: BLK-001\n"
                "  issue: broken\n\n"
                "## Final Gate Recommendation\n"
                "- proceed_to_finalizer: no\n",
                encoding="utf-8",
            )

            self.assertFalse(continuity_allows_finalizer(review))

            review.write_text(
                "# Chapter 1 Continuity Report\n\n"
                "## Metadata\n"
                "- status: PASS_WITH_NOTES\n\n"
                "## Blockers\n"
                "- 없음\n\n"
                "## Final Gate Recommendation\n"
                "- proceed_to_finalizer: yes\n",
                encoding="utf-8",
            )

            self.assertTrue(continuity_allows_finalizer(review))

    def test_writer_task_skips_blocked_previous_final_and_uses_review_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_dir = root / "projects" / "book_001"
            state = ensure_project(project_dir, title="Orbit", genre="SF")
            state["current_chapter"] = 2
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "writer.md").write_text("You are the writer.", encoding="utf-8")
            (project_dir / "outline.md").write_text(
                "| chapter | title |\n|---|---|\n| 1 | One |\n| 2 | Two |\n",
                encoding="utf-8",
            )
            (project_dir / "chapters" / "ch001_final.md").write_text(
                "## Metadata\n- final_status: BLOCKED\n",
                encoding="utf-8",
            )
            (project_dir / "chapters" / "ch001_edited.md").write_text("edited", encoding="utf-8")
            (project_dir / "reviews" / "ch001_continuity.md").write_text("review", encoding="utf-8")

            task = build_task(
                root=root,
                project_dir=project_dir,
                action=get_action("4"),
                state=state,
                user_request="",
            )
            task_text = task.task_file.read_text(encoding="utf-8")

            self.assertIn("이전 챕터 최종본 주의", task_text)
            self.assertNotIn("- projects/book_001/chapters/ch001_final.md (있음)", task_text)
            self.assertIn("- projects/book_001/chapters/ch001_edited.md (있음)", task_text)
            self.assertIn("- projects/book_001/reviews/ch001_continuity.md (있음)", task_text)

    def test_load_project_rolls_back_to_first_incomplete_chapter_gap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "projects" / "book_001"
            state = ensure_project(project_dir, title="Orbit", genre="SF")
            (project_dir / "outline.md").write_text(
                "| chapter | title |\n|---|---|\n| 1 | One |\n| 2 | Two |\n| 3 | Three |\n| 4 | Four |\n",
                encoding="utf-8",
            )
            for chapter in ["ch001", "ch002"]:
                (project_dir / "chapters" / f"{chapter}_final.md").write_text(
                    "## Metadata\n- final_status: READY\n",
                    encoding="utf-8",
                )
            (project_dir / "chapters" / "ch003_final.md").write_text(
                "## Metadata\n- final_status: BLOCKED\n",
                encoding="utf-8",
            )
            state["current_chapter"] = 4
            state["completed_chapters"] = [1, 2, 3]
            save_project(project_dir, state)

            reloaded = load_project(project_dir)

            self.assertEqual(reloaded["completed_chapters"], [1, 2])
            self.assertEqual(reloaded["current_chapter"], 3)

    def test_project_status_summarizes_chapter_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "projects" / "book_001"
            state = ensure_project(project_dir, title="Orbit", genre="SF")
            (project_dir / "outline.md").write_text(
                "| chapter | title |\n|---|---|\n| 1 | Start |\n| 2 | Next |\n",
                encoding="utf-8",
            )
            state["completed_chapters"] = [1]
            state["current_chapter"] = 2
            (project_dir / "chapters" / "ch001_final.md").write_text(
                "## Metadata\n- final_status: READY\n",
                encoding="utf-8",
            )

            status_file = write_project_status(project_dir, state)
            status_text = status_file.read_text(encoding="utf-8")

            self.assertIn("total_chapters: 2", status_text)
            self.assertIn("| ch001 | Start | done |", status_text)
            self.assertIn("| ch002 | Next | current |", status_text)
            self.assertEqual(chapter_id(2), "ch002")

    def test_auto_brief_infers_short_and_long_targets(self):
        self.assertEqual(_infer_target_pages("10p 분량의 단편소설을 써줘"), 10)
        self.assertEqual(_infer_target_chapters("10p 분량의 단편소설을 써줘", 10), 1)
        self.assertEqual(_infer_target_chapters("300p 분량의 장편소설을 써줘", 300), 12)

    def test_auto_project_selection_honors_book_number_mention_when_active_differs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir) / "projects"
            book1_dir, book1_state = create_project(projects_dir, title="Demon Girl", genre="Thriller")
            book2_dir, _ = create_project(projects_dir, title="Other Book", genre="SF")

            project_dir, state = _select_or_create_auto_project(
                projects_dir=projects_dir,
                active_project_dir=book2_dir,
                ceo_request="book1 continue from chapter 4, do not create a new book",
            )

            self.assertEqual(project_dir, book1_dir)
            self.assertEqual(state["project_id"], book1_state["project_id"])
            self.assertEqual(list_projects(projects_dir), ["book_001", "book_002"])

    def test_auto_project_selection_understands_unpadded_book_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir) / "projects"
            first_dir, _ = create_project(projects_dir, title="First", genre="Thriller")
            second_dir, second_state = create_project(projects_dir, title="Second", genre="Mystery")

            project_dir, state = _select_or_create_auto_project(
                projects_dir=projects_dir,
                active_project_dir=first_dir,
                ceo_request="book2 이어서 계속",
            )

            self.assertEqual(project_dir, second_dir)
            self.assertEqual(state["project_id"], second_state["project_id"])
            self.assertEqual(list_projects(projects_dir), ["book_001", "book_002"])

    def test_full_automation_dummy_runs_to_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for dirname in ["prompts", "tasks", "logs", "projects"]:
                (root / dirname).mkdir()
            for prompt in [
                "producer.md",
                "planner.md",
                "outliner.md",
                "writer.md",
                "editor.md",
                "continuity_checker.md",
                "finalizer.md",
                "packager.md",
            ]:
                (root / "prompts" / prompt).write_text("Role prompt\n\n## Next Handoff\n", encoding="utf-8")
            active_project, active_state = create_project(root / "projects", title="Active", genre="SF")
            active_state["mode"] = "dummy"
            save_project(active_project, active_state)
            save_active_project_id(root / "projects", active_state["project_id"])

            summary = run_full_automation(
                root=root,
                projects_dir=root / "projects",
                log_file=root / "logs" / "runs.jsonl",
                ceo_request="10p 분량의 단편소설을 써줘. 제목: 테스트 단편",
                active_project_dir=active_project,
            )

            self.assertTrue(summary.success)
            self.assertTrue((summary.project_dir / "final" / "book_final.md").exists())
            self.assertIn("outliner:ch001", summary.completed_steps)
            state = load_project(summary.project_dir)
            self.assertEqual(state["phase"], "packaged")
            self.assertEqual(state["total_chapters"], 1)
            self.assertEqual(state["completed_chapters"], [1])

    def test_full_automation_continue_reuses_existing_setup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for dirname in ["prompts", "tasks", "logs", "projects"]:
                (root / dirname).mkdir()
            for prompt in [
                "producer.md",
                "planner.md",
                "outliner.md",
                "writer.md",
                "editor.md",
                "continuity_checker.md",
                "finalizer.md",
                "packager.md",
            ]:
                (root / "prompts" / prompt).write_text("Role prompt\n\n## Next Handoff\n", encoding="utf-8")
            project_dir, state = create_project(root / "projects", title="악마소녀", genre="스릴러")
            state["mode"] = "dummy"
            state["current_chapter"] = 2
            state["total_chapters"] = 2
            state["completed_chapters"] = [1]
            save_project(project_dir, state)
            (project_dir / "production_plan.md").write_text("existing production plan", encoding="utf-8")
            (project_dir / "story_bible.md").write_text("existing bible", encoding="utf-8")
            (project_dir / "outline.md").write_text(
                "| chapter | title | purpose | conflict | turn | ending_hook |\n"
                "|---|---|---|---|---|---|\n"
                "| 1 | One | p | c | t | h |\n"
                "| 2 | Two | p | c | t | h |\n",
                encoding="utf-8",
            )
            (project_dir / "chapters" / "ch001_final.md").write_text(
                "## Metadata\n- final_status: READY\n\n## Final Body\nchapter one\n",
                encoding="utf-8",
            )
            save_active_project_id(root / "projects", state["project_id"])

            summary = run_full_automation(
                root=root,
                projects_dir=root / "projects",
                log_file=root / "logs" / "runs.jsonl",
                ceo_request="악마소녀 계속 써줘",
                active_project_dir=project_dir,
            )

            self.assertTrue(summary.success)
            self.assertIn("producer:reuse", summary.completed_steps)
            self.assertNotIn("planner", summary.completed_steps)
            self.assertIn("outliner:ch002", summary.completed_steps)
            self.assertEqual((project_dir / "story_bible.md").read_text(encoding="utf-8"), "existing bible")

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
            command = popen.call_args.args[0]
            self.assertIn("--model", command)
            self.assertEqual(command[command.index("--model") + 1], "gpt-5.5")
            self.assertIn("--sandbox", command)
            self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")

    def test_live_runner_allows_model_override_from_environment(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = []
                self.returncode = 0

            def wait(self):
                return self.returncode

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "tasks" / "current_task.md"
            expected_output = root / "projects" / "book_001" / "story_bible.md"
            task_file.parent.mkdir(parents=True)
            task_file.write_text("## Mission\nPlan the book.\n", encoding="utf-8")

            with patch("harness.codex_runner._resolve_codex_executable", return_value=Path("codex")):
                with patch("harness.codex_runner.subprocess.Popen", return_value=FakeProcess()) as popen:
                    with patch.dict(os.environ, {"CODEX_MODEL": "gpt-4.1"}, clear=False):
                        run = run_codex(
                            root=root,
                            task_file=task_file,
                            expected_output=expected_output,
                            role="planner",
                            mode="live",
                        )

            self.assertTrue(run.success)
            command = popen.call_args.args[0]
            self.assertEqual(command[command.index("--model") + 1], "gpt-4.1")

    def test_codex_resolver_prefers_desktop_app_binary_over_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            local_app_data = Path(temp_dir)
            app_codex = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe"
            app_codex.parent.mkdir(parents=True)
            app_codex.write_text("", encoding="utf-8")

            with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=False):
                with patch("harness.codex_runner.shutil.which", return_value="C:\\old\\codex.cmd"):
                    resolved = _resolve_codex_executable()

            self.assertEqual(resolved, app_codex)

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

    def test_result_checker_rejects_incomplete_role_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "projects" / "book_001" / "chapters" / "ch001_draft.md"
            output.parent.mkdir(parents=True)
            output.write_text("# Chapter 1 Draft\n\n## Metadata\n- project_id: book_001\n", encoding="utf-8")

            check = check_result(output, role="writer")

            self.assertFalse(check.success)
            self.assertIn("incomplete", check.message)
            self.assertIn("## Draft Body", check.message)

    def test_auto_custom_step_retries_incomplete_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for dirname in ["prompts", "tasks", "logs", "projects"]:
                (root / dirname).mkdir()
            (root / "prompts" / "writer.md").write_text("Role prompt\n\n## Next Handoff\n", encoding="utf-8")
            project_dir, state = create_project(root / "projects", title="Retry", genre="SF")

            calls = {"count": 0}

            def fake_run_codex(*, root, task_file, expected_output, role, mode):
                calls["count"] += 1
                if calls["count"] == 1:
                    expected_output.parent.mkdir(parents=True, exist_ok=True)
                    expected_output.write_text("# Chapter 1 Draft\n\n## Metadata\n", encoding="utf-8")
                else:
                    expected_output.write_text(
                        "# Chapter 1 Draft\n\n"
                        "## Metadata\n- project_id: book_001\n\n"
                        "## Draft Body\n본문\n\n"
                        "## Draft Notes\n- note\n\n"
                        "## Next Handoff\n- next_role: Editor\n\n"
                        "## 다음 작업 메모\n계속\n",
                        encoding="utf-8",
                    )
                return CodexRunResult(True, mode, "ok", 0, expected_output)

            with patch("harness.automation.run_codex", side_effect=fake_run_codex):
                result = _run_custom_step(
                    root=root,
                    project_dir=project_dir,
                    log_file=root / "logs" / "runs.jsonl",
                    state=state,
                    role="writer",
                    menu="test-writer",
                    prompt_file="writer.md",
                    label="retry writer",
                    goal="write draft",
                    output_path=project_dir / "chapters" / "ch001_draft.md",
                    ceo_request="test",
                    mode="live",
                )

            self.assertTrue(result.success)
            self.assertEqual(calls["count"], 2)

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
