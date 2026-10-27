"""Browser witness for one received-lesson attempt.

Starts an ephemeral localhost server, receives one custom lesson, and lets
the browser driver enable an injected MIDI input, perform one attempt, cancel
another, and show an append failure. Physical MIDI and audio are not certified.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_API_PREFIX,
    LESSON_DELIVERY_PREVIEW_PATH,
    LESSON_PRACTICE_CHOICE_PATH,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.local_server import serve_mvp_directory

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "resources" / "lesson" / "examples" / "local_midi_basic.json"
TITLE = "Stage 8 Received Etude"
CHROME_ENV = "DO016_CHROME_EXECUTABLE"
PUPPETEER_ENV = "DO016_PUPPETEER_MODULE"
DEFAULT_CHROME = Path("/usr/local/bin/google-chrome")
DEFAULT_PUPPETEER = Path(
    "/tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js"
)


class BrowserConfigError(RuntimeError):
    """The witness was given a browser it cannot launch."""


def resolve_browser_config(chrome: str | None, puppeteer: str | None) -> tuple[Path, Path]:
    """Flags win, then the environment, then the documented Linux defaults."""

    chrome_text = chrome or os.environ.get(CHROME_ENV) or str(DEFAULT_CHROME)
    puppeteer_text = puppeteer or os.environ.get(PUPPETEER_ENV) or str(DEFAULT_PUPPETEER)
    chrome_path = Path(chrome_text).expanduser()
    puppeteer_path = Path(puppeteer_text).expanduser()
    if not chrome_path.is_file():
        raise BrowserConfigError(f"chrome executable was not found: {chrome_path}")
    if not puppeteer_path.is_file():
        raise BrowserConfigError(f"puppeteer module was not found: {puppeteer_path}")
    return chrome_path, puppeteer_path


def _node_modules(puppeteer_path: Path) -> str:
    for parent in puppeteer_path.parents:
        if parent.name == "node_modules":
            return str(parent)
    return str(puppeteer_path.parent)


def _request(base: str, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            return response.status, json.loads(payload or b"{}")
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            parsed = json.loads(payload or b"{}")
        except json.JSONDecodeError:
            parsed = {}
        return exc.code, parsed


def _receive(base: str, assignment: object, delivery_id: str) -> None:
    status, body = _request(
        base,
        "POST",
        LESSON_DELIVERY_API_PREFIX,
        delivery_to_dict(
            envelope_for(
                assignment,
                delivery_id=delivery_id,
                sender_ref="teacher-ana",
                recipient_ref="student-bo",
            )
        ),
    )
    if status != 201:
        raise RuntimeError(f"receive {delivery_id} failed: {status} {body}")


def _preview(base: str, delivery_id: str) -> dict:
    query = urllib.parse.urlencode({"delivery_id": delivery_id})
    status, body = _request(base, "GET", f"{LESSON_DELIVERY_PREVIEW_PATH}?{query}")
    if status != 200 or body.get("preview_status") != "READY":
        raise RuntimeError(f"preview {delivery_id} failed: {status} {body}")
    return body


def _choose(base: str, preview: dict) -> None:
    status, body = _request(
        base,
        "POST",
        LESSON_PRACTICE_CHOICE_PATH,
        {
            "delivery_id": preview["delivery_id"],
            "expected_assignment_artifact_digest": preview["assignment_artifact_digest"],
            "expected_assignment_behavior_digest": preview["assignment_behavior_digest"],
        },
    )
    if status not in (200, 201) or body.get("choice_status") != "CHOSEN_FOR_PRACTICE":
        raise RuntimeError(f"choice {preview['delivery_id']} failed: {status} {body}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--chrome-executable")
    parser.add_argument("--puppeteer-module")
    args = parser.parse_args(argv)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    try:
        chrome_path, puppeteer_path = resolve_browser_config(
            args.chrome_executable,
            args.puppeteer_module,
        )
    except BrowserConfigError as exc:
        (output / "driver.log").write_text(f"{exc}\n", encoding="utf-8")
        return 2

    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["identity"]["title"] = TITLE
    assignment = deserialize_lesson_assignment(json.dumps(raw))
    api = LocalLessonDeliveryApi()
    server = None
    try:
        server, _thread, url = serve_mvp_directory(
            ROOT / "web" / "mvp1",
            open_browser=False,
            lesson_delivery_api=api,
        )
        base = url.rsplit("/", 1)[0]
        delivery_id = "delivery-stage8"
        _receive(base, assignment, delivery_id)
        preview = _preview(base, delivery_id)
        if preview.get("title") != TITLE:
            raise RuntimeError(f"preview title was {preview.get('title')!r}")
        _choose(base, preview)
        manifest = {
            "base": base,
            "delivery_id": delivery_id,
            "title": TITLE,
            "injected_midi": True,
            "chrome_executable": str(chrome_path),
            "puppeteer_module": str(puppeteer_path),
        }
        (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        env = os.environ.copy()
        node_modules = _node_modules(puppeteer_path)
        node_path = env.get("NODE_PATH", "")
        env["NODE_PATH"] = (
            node_modules if not node_path else os.pathsep.join((node_modules, node_path))
        )
        env[CHROME_ENV] = str(chrome_path)
        env[PUPPETEER_ENV] = str(puppeteer_path)
        completed = subprocess.run(
            [
                "node",
                str(ROOT / "web" / "mvp1" / "tests" / "do016_received_attempt_capture.mjs"),
                base,
                str(output),
                delivery_id,
            ],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        (output / "driver.log").write_text(
            completed.stdout + completed.stderr,
            encoding="utf-8",
        )
        return completed.returncode
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    sys.exit(main())
