#!/usr/bin/env python3
"""Find an element in the `android layout` output, then list it, tap it or type into it."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

POINT = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
TEXT_KEYS = ("text",)
DESC_KEYS = ("content-desc", "contentDesc")
ID_KEYS = ("resource-id", "resourceId")
FOCUS_TIMEOUT = 3.0
NO_MATCH = "no element matches; if it may be off-screen, scroll its container and retry"


class UiError(Exception):
    pass


def run(command):
    try:
        return subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        raise UiError(f"'{command[0]}' is not on PATH; install the Android CLI and SDK Platform-Tools")


def fetch_layout(serial):
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "layout.json")
        command = ["android", "layout", f"--output={path}"]
        if serial:
            command.append(f"--device={serial}")
        result = run(command)
        if result.returncode != 0 or not os.path.exists(path):
            message = (result.stderr or result.stdout).strip() or "android layout failed"
            raise UiError(f"{message}\nIf the screen shows a WebView or an animation, use `android screen capture --annotate`.")
        with open(path, encoding="utf-8") as file:
            return json.load(file)


def elements(node):
    if isinstance(node, list):
        for child in node:
            yield from elements(child)
    elif isinstance(node, dict):
        if "center" in node or "bounds" in node:
            yield node
        for value in node.values():
            if isinstance(value, (list, dict)):
                yield from elements(value)


def field(element, keys):
    for key in keys:
        if element.get(key):
            return str(element[key])
    return ""


def has_flag(element, key, flag):
    return flag in {str(value).lower() for value in element.get(key, [])}


def is_off_screen(element):
    return any(str(element.get(key, "")).lower() == "true" for key in ("off-screen", "hidden"))


def center(element):
    points = POINT.findall(str(element.get("center", "")))
    if points:
        return int(points[0][0]), int(points[0][1])
    points = POINT.findall(str(element.get("bounds", "")))
    if len(points) == 2:
        (left, top), (right, bottom) = [(int(x), int(y)) for x, y in points]
        return (left + right) // 2, (top + bottom) // 2
    raise UiError(f"element has no coordinates: {summary(element)}")


def text_matches(actual, expected, exact):
    return actual == expected if exact else expected.casefold() in actual.casefold()


def id_matches(actual, expected):
    if not actual:
        return False
    if "/" in actual and "/" in expected:
        return actual == expected
    return actual.rsplit("/", 1)[-1] == expected.rsplit("/", 1)[-1]


def find(layout, text=None, desc=None, resource_id=None, exact=False):
    matches = []
    for element in elements(layout):
        if text is not None and not text_matches(field(element, TEXT_KEYS), text, exact):
            continue
        if desc is not None and not text_matches(field(element, DESC_KEYS), desc, exact):
            continue
        if resource_id is not None and not id_matches(field(element, ID_KEYS), resource_id):
            continue
        matches.append(element)
    return matches


def on_screen(matches):
    return [element for element in matches if not is_off_screen(element)]


def select(matches, index):
    visible = on_screen(matches)
    if not matches:
        raise UiError(NO_MATCH)
    if not visible:
        raise UiError("only off-screen or hidden elements match; scroll their scrollable container and retry")
    if index is None:
        if len(visible) > 1:
            listing = "\n".join(f"  [{i}] {summary(element)}" for i, element in enumerate(visible))
            raise UiError(f"{len(visible)} on-screen elements match; pass --index:\n{listing}")
        return visible[0]
    if not 0 <= index < len(visible):
        raise UiError(f"--index {index} is out of range; {len(visible)} on-screen elements match")
    return visible[index]


def summary(element):
    parts = {
        "text": field(element, TEXT_KEYS),
        "desc": field(element, DESC_KEYS),
        "id": field(element, ID_KEYS),
        "center": element.get("center", ""),
        "interactions": ",".join(element.get("interactions", [])),
        "state": ",".join(element.get("state", [])),
    }
    return " ".join(f"{key}={json.dumps(value)}" for key, value in parts.items() if value)


def wait_for_matches(serial, criteria, timeout):
    deadline = time.monotonic() + timeout
    while True:
        matches = find(fetch_layout(serial), **criteria)
        remaining = deadline - time.monotonic()
        if on_screen(matches) or remaining <= 0:
            return matches
        time.sleep(min(1.0, remaining))


def adb_shell(serial, *args):
    command = ["adb", *(["-s", serial] if serial else []), "shell", *args]
    result = run(command)
    if result.returncode != 0:
        raise UiError((result.stderr or result.stdout).strip() or f"adb shell {' '.join(args)} failed")


def tap(serial, element):
    x, y = center(element)
    adb_shell(serial, "input", "tap", str(x), str(y))
    return x, y


def wait_for_focus(serial, timeout):
    deadline = time.monotonic() + timeout
    while True:
        if any(has_flag(element, "state", "focused") for element in elements(fetch_layout(serial))):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.5, remaining))


def type_text(serial, element, text):
    tap(serial, element)
    if not wait_for_focus(serial, FOCUS_TIMEOUT):
        raise UiError(f"tapped {summary(element)} but no element is focused; tap the text field itself")
    adb_shell(serial, "input", "text", shlex.quote(text.replace(" ", "%s")))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Find an element in the current `android layout` and list it, tap it or type into it. "
        "Criteria combine with AND. Without --tap or --type, matching elements are listed.",
    )
    parser.add_argument("--text", help="match element text (case-insensitive substring)")
    parser.add_argument("--desc", help="match content description (case-insensitive substring)")
    parser.add_argument("--id", dest="resource_id", help="match resource ID, with or without the 'package:id/' prefix")
    parser.add_argument("--exact", action="store_true", help="require --text and --desc to match exactly")
    parser.add_argument("--index", type=int, help="pick the Nth on-screen match, counting from 0")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--tap", action="store_true", help="tap the center of the element")
    action.add_argument("--type", dest="type_text", metavar="TEXT", help="tap the element, wait for focus, then type TEXT")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for a match to appear (default: 10)")
    parser.add_argument("--serial", "-s", help="device serial (default: ANDROID_SERIAL)")
    args = parser.parse_args(argv)
    if args.text is None and args.desc is None and args.resource_id is None:
        parser.error("pass at least one of --text, --desc or --id")
    return args


def main(argv=None):
    args = parse_args(argv)
    serial = args.serial or os.environ.get("ANDROID_SERIAL")
    criteria = {"text": args.text, "desc": args.desc, "resource_id": args.resource_id, "exact": args.exact}
    try:
        matches = wait_for_matches(serial, criteria, args.timeout)
        if args.tap:
            element = select(matches, args.index)
            x, y = tap(serial, element)
            print(f"tapped {x},{y} {summary(element)}")
        elif args.type_text is not None:
            element = select(matches, args.index)
            type_text(serial, element, args.type_text)
            print(f"typed into {summary(element)}")
        else:
            if not matches:
                raise UiError(NO_MATCH)
            for i, element in enumerate(on_screen(matches)):
                print(f"[{i}] {summary(element)}")
            for element in matches:
                if is_off_screen(element):
                    print(f"[not visible] {summary(element)}")
    except UiError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
