"""Browser witness for opening a received lesson.

Starts an ephemeral localhost server, seeds deliveries through the Stage 1
HTTP route, creates a choice through the Stage 3 HTTP route, and lets the
browser driver open practice. Corrupt, removed, and stale-pin cases are
written only into this process's in-memory repositories. There is no
production hook for them.

The process exits non-zero when the browser driver reports a failure.
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
from dataclasses import replace
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
OTHER_DIGEST = "sha256:" + "ab" * 32


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


def _receive(base: str, assignment, delivery_id: str) -> None:
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
    args = parser.parse_args(argv)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    assignment = deserialize_lesson_assignment(EXAMPLE.read_text(encoding="utf-8"))
    api = LocalLessonDeliveryApi()
    server, _thread, url = serve_mvp_directory(
        ROOT / "web" / "mvp1",
        open_browser=False,
        lesson_delivery_api=api,
    )
    base = url.rsplit("/", 1)[0]
    try:
        practice_id = "delivery-practice"
        missing_id = "delivery-missing-choice"
        corrupt_id = "delivery-corrupt"
        removed_id = "delivery-removed"
        stale_id = "delivery-stale"
        for delivery_id in (practice_id, missing_id, corrupt_id, removed_id, stale_id):
            _receive(base, assignment, delivery_id)
        _choose(base, _preview(base, stale_id))

        corrupt = api.service.get(corrupt_id)
        api.service.repository._deliveries[corrupt_id] = replace(
            corrupt,
            assignment_artifact_digest=OTHER_DIGEST,
        )
        del api.service.repository._deliveries[removed_id]
        stale_choice = api.choices._choices[stale_id]
        api.choices._choices[stale_id] = replace(
            stale_choice,
            assignment_artifact_digest=OTHER_DIGEST,
        )

        manifest = {
            "base": base,
            "practice_id": practice_id,
            "missing_choice_id": missing_id,
            "corrupt_id": corrupt_id,
            "removed_id": removed_id,
            "stale_id": stale_id,
        }
        (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        env = os.environ.copy()
        node_path = env.get("NODE_PATH", "")
        puppeteer_path = "/tmp/inbox-smoke/node_modules"
        env["NODE_PATH"] = puppeteer_path if not node_path else f"{puppeteer_path}:{node_path}"
        completed = subprocess.run(
            [
                "node",
                str(ROOT / "web" / "mvp1" / "tests" / "do016_received_practice_capture.mjs"),
                base,
                str(output),
            ],
            cwd=ROOT,
            env=env,
            check=False,
        )
        return completed.returncode
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
