import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "testing/android-emulator/scripts"))
import ui

FLAT = [
    {"text": "Search settings", "resource-id": "search_action_bar_title", "center": "[430,762]"},
    {"content-desc": "Profile picture", "interactions": ["clickable"], "center": "[1136,396]", "resource-id": "account_avatar"},
    {"text": "Network & internet", "center": "[640,1021]"},
    {"text": "Network settings", "center": "[640,2900]", "off-screen": True},
]


class LayoutParsingTests(unittest.TestCase):
    def test_collects_elements_from_flat_lists_and_nested_trees(self):
        tree = {"class": "Root", "bounds": "[0,0][100,100]", "children": [{"text": "A", "center": "[1,2]", "children": [{"text": "B", "bounds": "[0,0][10,10]"}]}]}
        self.assertEqual(len(list(ui.elements(FLAT))), 4)
        self.assertEqual([e.get("text") for e in ui.elements(tree)], [None, "A", "B"])

    def test_center_prefers_center_and_falls_back_to_bounds(self):
        self.assertEqual(ui.center({"center": "[152,23]", "bounds": "[0,0][0,0]"}), (152, 23))
        self.assertEqual(ui.center({"bounds": "[100,200][400, 600]"}), (250, 400))
        with self.assertRaises(ui.UiError):
            ui.center({"text": "none"})


class MatchingTests(unittest.TestCase):
    def test_text_is_case_insensitive_substring_unless_exact(self):
        self.assertEqual(len(ui.find(FLAT, text="network")), 2)
        self.assertEqual(ui.find(FLAT, text="Network & internet", exact=True), [FLAT[2]])
        self.assertEqual(ui.find(FLAT, text="network", exact=True), [])

    def test_resource_id_matches_with_or_without_package_prefix(self):
        full = [{"resource-id": "com.example:id/title", "center": "[1,1]"}]
        self.assertEqual(ui.find(full, resource_id="title"), full)
        self.assertEqual(ui.find(full, resource_id="com.example:id/title"), full)
        self.assertEqual(ui.find(full, resource_id="com.other:id/title"), [])
        self.assertEqual(ui.find(FLAT, resource_id="com.android.settings:id/account_avatar"), [FLAT[1]])

    def test_documented_camel_case_keys_are_supported(self):
        layout = [{"contentDesc": "Back", "resourceId": "nav_back", "center": "[1,1]"}]
        self.assertEqual(ui.find(layout, desc="back", resource_id="nav_back"), layout)

    def test_selection_rejects_ambiguity_and_off_screen_only_matches(self):
        with self.assertRaises(ui.UiError):
            ui.select(ui.find(FLAT, text="in"), None)
        self.assertEqual(ui.select(ui.find(FLAT, text="in"), 1), FLAT[2])
        self.assertEqual(ui.select(ui.find(FLAT, text="settings"), None), FLAT[0])
        with self.assertRaisesRegex(ui.UiError, "off-screen"):
            ui.select([FLAT[3]], None)
        with self.assertRaisesRegex(ui.UiError, "out of range"):
            ui.select(FLAT, 5)


TREE = [
    {
        "class": "android.widget.ScrollView",
        "resource-id": "com.android.settings:id/settings_homepage_container",
        "interactions": ["SCROLLABLE"],
        "center": "[640,1470]",
        "children": [
            {"class": "android.widget.EditText", "resource-id": "com.android.settings:id/search", "text": "Search settings", "interactions": ["CLICKABLE", "FOCUSABLE", "EDITABLE"], "center": "[712,264]"},
            {"class": "android.widget.TextView", "text": "Search tips", "center": "[640,3000]", "hidden": True},
        ],
    }
]


class CurrentLayoutFormatTests(unittest.TestCase):
    def test_nested_tree_with_package_ids_and_hidden_elements(self):
        self.assertEqual(ui.select(ui.find(TREE, text="search"), None)["class"], "android.widget.EditText")
        self.assertEqual(len(ui.find(TREE, resource_id="search")), 1)
        with self.assertRaisesRegex(ui.UiError, "hidden"):
            ui.select(ui.find(TREE, text="tips"), None)

    def test_flags_are_case_insensitive(self):
        self.assertTrue(ui.has_flag({"state": ["FOCUSED"]}, "state", "focused"))
        self.assertTrue(ui.has_flag({"state": ["focused"]}, "state", "focused"))
        self.assertFalse(ui.has_flag({"interactions": ["FOCUSABLE"]}, "state", "focused"))


class FakeDevice:
    def __init__(self, layouts):
        self.layouts = list(layouts)
        self.commands = []

    def run(self, command, **kwargs):
        self.commands.append(command)
        if command[0] == "android":
            output = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--output="))
            layout = self.layouts.pop(0) if len(self.layouts) > 1 else self.layouts[0]
            Path(output).write_text(json.dumps(layout))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def adb(self):
        return [c for c in self.commands if c[0] == "adb"]


class CommandTests(unittest.TestCase):
    def run_main(self, device, argv):
        with patch.object(ui.subprocess, "run", side_effect=device.run), \
                patch.object(ui.time, "sleep"), \
                patch.dict(ui.os.environ, {}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            return ui.main(argv), stderr.getvalue()

    def test_tap_sends_center_to_selected_device(self):
        device = FakeDevice([FLAT])
        code, _ = self.run_main(device, ["--desc", "profile", "--tap", "-s", "emulator-5556"])
        self.assertEqual(code, 0)
        self.assertIn("--device=emulator-5556", device.commands[0])
        self.assertEqual(device.adb(), [["adb", "-s", "emulator-5556", "shell", "input", "tap", "1136", "396"]])

    def test_type_waits_for_focus_and_quotes_text_for_the_device_shell(self):
        focused = [dict(FLAT[0], state=["focused"])]
        device = FakeDevice([FLAT, FLAT, focused])
        code, _ = self.run_main(device, ["--text", "search", "--type", "AT&T it's $5"])
        self.assertEqual(code, 0)
        self.assertEqual(device.adb()[-1], ["adb", "shell", "input", "text", "'AT&T%sit'\"'\"'s%s$5'"])

    def test_type_accepts_uppercase_focus_state_in_tree_layouts(self):
        focused = json.loads(json.dumps(TREE))
        focused[0]["children"][0]["state"] = ["FOCUSED"]
        device = FakeDevice([TREE, TREE, focused])
        code, _ = self.run_main(device, ["--id", "com.android.settings:id/search", "--type", "hi"])
        self.assertEqual(code, 0)
        self.assertEqual(device.adb()[-1], ["adb", "shell", "input", "text", "hi"])

    def test_type_fails_when_nothing_gets_focus(self):
        device = FakeDevice([FLAT])
        with patch.object(ui.time, "monotonic", side_effect=[0, 0, 0, 0, 10, 10]):
            code, stderr = self.run_main(device, ["--text", "search", "--type", "x", "--timeout", "0"])
        self.assertEqual(code, 1)
        self.assertIn("no element is focused", stderr)
        self.assertEqual(len(device.adb()), 1)

    def test_ambiguous_tap_fails_without_touching_the_device(self):
        device = FakeDevice([FLAT])
        code, stderr = self.run_main(device, ["--text", "in", "--tap", "--timeout", "0"])
        self.assertEqual(code, 1)
        self.assertIn("pass --index", stderr)
        self.assertEqual(device.adb(), [])


if __name__ == "__main__":
    unittest.main()
