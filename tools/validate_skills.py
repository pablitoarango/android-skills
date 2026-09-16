#!/usr/bin/env python3
"""Validate the skills in this repository. Exits non-zero when any check fails."""

import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SKILL_REFERENCE = re.compile(r"`((?:android|compose|gradle|migrate)-[a-z0-9-]+)`")
MARKDOWN_LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)")
FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
GOOGLE_SOURCE_LINK = re.compile(
    r"\]\(https://(?:developer\.android\.com|developers\.google\.com|android\.googlesource\.com)/[^)]+\)"
    r"|\]\(https://github\.com/android/[^)]+\)"
)
MAX_DESCRIPTION_LENGTH = 400
MAX_SKILL_LINES = 500
EM_DASH = chr(0x2014)
NOT_SKILLS = {"gradle-profiler"}
TEXT_SUFFIXES = {".md", ".py", ".sh", ".ps1", ".json", ".yml"}

errors: list[str] = []


def fail(path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def parse_frontmatter(path: Path) -> dict:
    text = read_text(path)
    if not text.startswith("---\n"):
        fail(path, "must start with a --- frontmatter block")
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        fail(path, "frontmatter block is not closed")
        return {}
    block = text[4:end]

    for line in block.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if key == "description" and not (value.startswith('"') and value.endswith('"')):
            fail(path, "description must be a double-quoted string so it is valid YAML")

    if yaml is not None:
        try:
            fields = yaml.safe_load(block)
        except yaml.YAMLError as error:
            fail(path, f"frontmatter is not valid YAML: {error}")
            return {}
        if not isinstance(fields, dict):
            fail(path, "frontmatter must be a YAML mapping")
            return {}
        return fields

    fields = {}
    for line in block.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                fail(path, f"'{key}' is not a valid double-quoted string")
        fields[key.strip()] = value
    return fields


def plugin_skill_directories() -> set[Path]:
    manifest = ROOT / ".claude-plugin" / "plugin.json"
    paths = json.loads(read_text(manifest)).get("skills", [])
    if isinstance(paths, str):
        paths = [paths]
    return {(ROOT / path).resolve() for path in paths}


def check_skills() -> set[str]:
    skill_files = sorted(ROOT.glob("*/*/SKILL.md"))
    if not skill_files:
        errors.append("no skills found under <category>/<skill>/SKILL.md")
    categories = plugin_skill_directories()
    names: set[str] = set()
    for skill in skill_files:
        folder = skill.parent.name
        fields = parse_frontmatter(skill)
        name = fields.get("name", "")
        description = fields.get("description", "")
        if name != folder:
            fail(skill, f"frontmatter name '{name}' must match folder '{folder}'")
        if not NAME_PATTERN.match(folder) or len(folder) > 64:
            fail(skill, "folder name must be kebab-case and at most 64 characters")
        if not isinstance(description, str) or not description:
            fail(skill, "frontmatter description is missing")
        elif len(description) > MAX_DESCRIPTION_LENGTH:
            fail(skill, f"description is {len(description)} characters; keep it at most {MAX_DESCRIPTION_LENGTH}")
        if folder in names:
            fail(skill, f"duplicate skill name '{folder}'")
        names.add(folder)
        text = read_text(skill)
        body = text.partition("\n---\n")[2].strip()
        if body.startswith("# "):
            body = body.partition("\n")[2].strip()
        source_line = body.splitlines()[0] if body else ""
        if not source_line.startswith("Sources of truth:"):
            fail(skill, "body must begin with Sources of truth: after optional title")
        elif not GOOGLE_SOURCE_LINK.search(source_line):
            fail(skill, "Sources of truth: must link to Google documentation or an official Android sample")
        if len(text.splitlines()) > MAX_SKILL_LINES:
            fail(skill, f"SKILL.md is longer than {MAX_SKILL_LINES} lines; move detail into a sibling file")
        if skill.parent.parent.resolve() not in categories:
            fail(skill, "category folder is not listed in .claude-plugin/plugin.json skills")
    return names


def check_markdown(names: set[str]) -> None:
    for markdown in sorted(ROOT.glob("**/*.md")):
        if ".git" in markdown.parts:
            continue
        text = FENCED_CODE.sub("", read_text(markdown))
        for reference in SKILL_REFERENCE.findall(text):
            if reference not in names and reference not in NOT_SKILLS:
                fail(markdown, f"references unknown skill `{reference}`")
        for target in MARKDOWN_LINK.findall(text):
            if not (markdown.parent / target.split("#")[0]).exists():
                fail(markdown, f"links to missing file '{target}'")


def check_em_dashes() -> None:
    for path in sorted(ROOT.rglob("*")):
        if ".git" in path.parts or not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        for number, line in enumerate(read_text(path).splitlines(), start=1):
            if EM_DASH in line:
                fail(path, f"line {number} contains an em dash; use a plain dash")


def check_scripts() -> None:
    for script in sorted(ROOT.glob("*/*/scripts/*.py")):
        try:
            py_compile.compile(str(script), doraise=True)
        except py_compile.PyCompileError as error:
            fail(script, f"does not compile: {error.msg}")
            continue
        result = subprocess.run(
            [sys.executable, script.name, "--help"],
            cwd=script.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            last_line = (result.stderr.strip().splitlines() or ["no output"])[-1]
            fail(script, f"--help failed: {last_line}")

    for script in sorted(ROOT.glob("**/*.sh")):
        if ".git" in script.parts:
            continue
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        if result.returncode != 0:
            fail(script, f"bash syntax error: {result.stderr.strip()}")

    powershell = shutil.which("pwsh")
    for script in sorted(ROOT.glob("**/*.ps1")):
        if ".git" in script.parts:
            continue
        if powershell is None:
            if os.environ.get("CI"):
                fail(script, "pwsh is required in CI to parse PowerShell scripts")
            continue
        command = (
            "$errors = $null; "
            f"[void][System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$errors); "
            "if ($errors) { $errors | ForEach-Object { $_.Message }; exit 1 }"
        )
        result = subprocess.run([powershell, "-NoProfile", "-Command", command], capture_output=True, text=True)
        if result.returncode != 0:
            fail(script, f"PowerShell parse error: {result.stdout.strip() or result.stderr.strip()}")


def check_skills_sh_json(names: set[str]) -> None:
    path = ROOT / "skills.sh.json"
    if not path.exists():
        errors.append("skills.sh.json: missing; skills.sh groups the repository page from it")
        return
    try:
        config = json.loads(read_text(path))
    except json.JSONDecodeError as error:
        fail(path, f"is not valid JSON: {error}")
        return
    groupings = config.get("groupings")
    if not isinstance(groupings, list) or not groupings:
        fail(path, "must list at least one grouping")
        return
    grouped: list[str] = []
    for group in groupings:
        if not isinstance(group, dict) or not group.get("title") or not group.get("skills"):
            fail(path, "every grouping needs a title and at least one skill")
            continue
        grouped.extend(group["skills"])
    for skill in sorted(set(grouped)):
        if skill not in names:
            fail(path, f"groups unknown skill '{skill}'")
        elif grouped.count(skill) > 1:
            fail(path, f"lists '{skill}' in more than one grouping")
    for skill in sorted(names - set(grouped)):
        fail(path, f"does not group '{skill}'")


def main() -> int:
    if yaml is None and os.environ.get("CI"):
        errors.append("PyYAML is required in CI to parse frontmatter (pip install pyyaml)")
    names = check_skills()
    check_markdown(names)
    check_skills_sh_json(names)
    check_em_dashes()
    check_scripts()
    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} problem(s) found")
        return 1
    parser_note = "" if yaml is not None else " (PyYAML not installed; frontmatter checked without a YAML parser)"
    print(f"{len(names)} skills valid{parser_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
