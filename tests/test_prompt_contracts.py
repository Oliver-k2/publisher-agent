import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = ROOT / "prompts"

ROLE_FILES = [
    "producer.md",
    "planner.md",
    "outliner.md",
    "writer.md",
    "editor.md",
    "continuity_checker.md",
    "finalizer.md",
]

REQUIRED_SECTIONS = [
    "## Mission",
    "## Required Inputs",
    "## Output Contract",
    "## Completion Criteria",
    "## Role Boundaries",
    "## Revision Loop",
]


class PromptContractTests(unittest.TestCase):
    def test_all_legacy_prompt_files_keep_harness_contract_sections(self):
        for filename in ROLE_FILES:
            with self.subTest(filename=filename):
                text = (PROMPT_DIR / filename).read_text(encoding="utf-8")
                for section in REQUIRED_SECTIONS:
                    self.assertIn(section, text)

    def test_prompts_explicitly_reference_current_task_and_next_handoff(self):
        for filename in ROLE_FILES:
            with self.subTest(filename=filename):
                text = (PROMPT_DIR / filename).read_text(encoding="utf-8")
                self.assertIn("tasks/current_task.md", text)
                self.assertIn("Next Handoff", text)


if __name__ == "__main__":
    unittest.main()
