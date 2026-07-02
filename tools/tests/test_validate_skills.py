import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_skills


class SourceHeaderTests(unittest.TestCase):
    def check_skill(self, body):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "ui/compose-example/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                '---\nname: compose-example\ndescription: "Example. Use when testing."\n---\n\n'
                + body,
                encoding="utf-8",
            )
            manifest = root / ".claude-plugin/plugin.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"skills": ["./ui"]}), encoding="utf-8")
            with patch.object(validate_skills, "ROOT", root), \
                    patch.object(validate_skills, "errors", []):
                validate_skills.check_skills()
                return list(validate_skills.errors)

    def test_accepts_source_line_after_title(self):
        self.assertEqual(self.check_skill(
            "# Example\n\nSources of truth: [Google](https://developer.android.com/develop/ui/compose/state).\n"
        ), [])

    def test_rejects_missing_misspelled_or_late_source_line(self):
        source = "Sources of truth: [Google](https://developer.android.com/develop/ui/compose/state).\n"
        for body in ["# Example\n\nText only.\n", source.replace("Sources", "Source"), "Text before sources.\n" + source]:
            with self.subTest(body=body):
                self.assertTrue(self.check_skill(body))

    def test_requires_a_google_source_link(self):
        self.assertTrue(self.check_skill("Sources of truth: Google.\n"))
        self.assertTrue(self.check_skill("Sources of truth: [Other](https://example.com/guide).\n"))


if __name__ == "__main__":
    unittest.main()
