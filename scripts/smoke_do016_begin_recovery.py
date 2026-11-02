"""Browser witness for keyed Begin recovery.

The child server is a normal local server. The only test hook is a monkeypatch
of preparation inside this process, released by a message on stdin.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import platform
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "web" / "mvp1" / "tests" / "do016_begin_recovery_capture.mjs"
VERIFIER = ROOT / "scripts" / "verify_do016_begin_recovery_evidence.py"
BEGIN_REQUEST_PATH = "/api/education/lesson-practice-begin-requests"
BEGIN_RECOVERY_PATH = "/api/education/lesson-practice-begin-recoveries"


def post_raw(base: str, path: str, raw: str) -> tuple[int, str]:
    """POST exactly these bytes and return the status and the response bytes."""

    request = urllib.request.Request(
        f"{base}{path}",
        data=raw.encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return int(response.status), base64.b64encode(response.read()).decode("ascii")
    except urllib.error.HTTPError as error:
        return int(error.code), base64.b64encode(error.read()).decode("ascii")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _node_version() -> str:
    try:
        return subprocess.check_output(["node", "--version"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _integration() -> Any:
    path = ROOT / "scripts" / "smoke_do016_integration.py"
    spec = importlib.util.spec_from_file_location("smoke_do016_integration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("integration witness is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_child(port: int) -> int:
    from master_all_strings.mvp.local_practice_preparation import LocalPracticePreparationService
    from master_all_strings.mvp.local_server import serve_mvp_directory

    release = threading.Event()
    real = LocalPracticePreparationService.prepare

    def blocked(self: Any, *args: object, **kwargs: object) -> Any:
        if not blocked.armed:  # type: ignore[attr-defined]
            return real(self, *args, **kwargs)
        blocked.armed = False  # type: ignore[attr-defined]
        sys.stdout.write(json.dumps({"event": "prepare-blocked"}) + "\n")
        sys.stdout.flush()
        release.wait(20)
        release.clear()
        return real(self, *args, **kwargs)

    blocked.armed = False  # type: ignore[attr-defined]
    LocalPracticePreparationService.prepare = blocked  # type: ignore[method-assign]

    from http.server import ThreadingHTTPServer

    from master_all_strings.mvp.lesson_delivery_api import LocalLessonDeliveryApi

    ThreadingHTTPServer.allow_reuse_address = True
    server, _thread, url = serve_mvp_directory(
        ROOT / "web" / "mvp1",
        host="127.0.0.1",
        port=port,
        open_browser=False,
        path="/lesson-inbox.html",
        lesson_delivery_api=LocalLessonDeliveryApi(),
    )
    base = url.rsplit("/", 1)[0]
    sys.stdout.write(json.dumps({"event": "listening", "base": base, "pid": os.getpid()}) + "\n")
    sys.stdout.flush()
    try:
        for line in sys.stdin:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("op") == "arm":
                blocked.armed = True  # type: ignore[attr-defined]
                sys.stdout.write(json.dumps({"event": "armed"}) + "\n")
                sys.stdout.flush()
            elif message.get("op") == "release":
                release.set()
            elif message.get("op") == "stop":
                break
    finally:
        release.set()
        server.shutdown()
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--child-server", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--chrome-executable")
    parser.add_argument("--puppeteer-module")
    args = parser.parse_args(argv)
    if args.child_server:
        if args.port is None:
            print("child server needs --port", file=sys.stderr)
            return 2
        return run_child(args.port)
    if args.output is None:
        print("output directory is required", file=sys.stderr)
        return 2
    integration = _integration()
    try:
        chrome, puppeteer = integration.resolve_browser_config(
            args.chrome_executable, args.puppeteer_module
        )
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "classification.json").write_text(
            json.dumps({"kind": "browser_launch", "detail": str(exc)}) + "\n",
            encoding="utf-8",
        )
        return 2
    return _run(args.output, chrome, puppeteer, integration)


def _run(output: Path, chrome: Path, puppeteer: Path, integration: Any) -> int:
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    port = integration.free_port()
    log = (output / "logs" / "server.log").open("w", encoding="utf-8")
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child-server", "--port", str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=log,
        text=True,
    )
    assert child.stdout is not None and child.stdin is not None
    ready_line = child.stdout.readline()
    queue: list[dict[str, Any]] = []
    lock = threading.Lock()

    def drain() -> None:
        assert child.stdout is not None
        for line in child.stdout:
            log.write(line)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                with lock:
                    queue.append(message)

    threading.Thread(target=drain, daemon=True).start()
    code = 1
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    dirty = _git("status", "--porcelain")
    try:
        if child.poll() is not None or not ready_line:
            raise RuntimeError("child exited before listening")
        ready = json.loads(ready_line)
        base = str(ready["base"])
        # The pid the server reports. On a Windows venv, Popen.pid is the launcher.
        server_pid = {"value": int(ready["pid"])}
        if not integration.wait_for_http(f"{base}/lesson-inbox.html", 15):
            raise RuntimeError("child did not answer HTTP")
        assignment = integration.custom_assignment()
        status, _body = integration.receive_delivery(base, assignment, integration.DELIVERY_ID)
        if status != 201:
            raise RuntimeError(f"receive failed: {status}")
        launch = {
            "base": base,
            "pid": int(ready["pid"]),
            "delivery_id": integration.DELIVERY_ID,
            "title": integration.TITLE,
            "chrome_executable": str(chrome),
            "puppeteer_module": str(puppeteer),
            "output": str(output),
        }
        (output / "launch.json").write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
        # The browser driver talks to this parent through a localhost socket.
        import socket

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        launch["control_port"] = int(sock.getsockname()[1])
        (output / "launch.json").write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
        env = os.environ.copy()

        def control() -> None:
            try:
                connection, _address = sock.accept()
            except OSError:
                return
            with connection:
                pending = b""
                while True:
                    try:
                        chunk = connection.recv(65536)
                    except OSError:
                        # The browser driver exited; there is nothing left to answer.
                        break
                    if not chunk:
                        break
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if not line.strip():
                            continue
                        reply = _control(
                            json.loads(line),
                            child,
                            base,
                            queue,
                            lock,
                            integration,
                            port,
                            output,
                            server_pid,
                        )
                        connection.sendall((json.dumps(reply) + "\n").encode())

        threading.Thread(target=control, daemon=True).start()
        driver = subprocess.Popen(
            ["node", str(CAPTURE), str(output / "launch.json")],
            cwd=ROOT,
            env=env,
            stdout=(output / "logs" / "driver.log").open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        code = driver.wait(timeout=180)
        browser = json.loads((output / "browser_evidence.json").read_text(encoding="utf-8"))
        packet = {
            "schema": "master_all_strings.do016_begin_recovery_evidence",
            "schema_version": "2",
            "complete": browser.get("complete") is True and code == 0,
            "failures": browser.get("failures"),
            "started_at": started_at,
            "tested_sha": _git("rev-parse", "HEAD"),
            "tested_tree": _git("rev-parse", "HEAD^{tree}"),
            "dirty": dirty,
            "python": platform.python_version(),
            "node": _node_version(),
            "chrome": browser.get("chrome"),
            "os": platform.platform(),
            "puppeteer_module": str(puppeteer),
            "transport": {
                "server_responses": "live",
                "network_failure": "simulated by aborting the page request",
                "not_sent_by_page": "posted by the harness to the live server",
            },
            "scenarios": browser.get("scenarios"),
            "exchanges": browser.get("exchanges"),
            "epochs": browser.get("epochs"),
            "notes": browser.get("notes"),
        }
        (output / "evidence.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        verified = subprocess.run(
            [sys.executable, str(VERIFIER), str(output / "evidence.json"), "--root", str(ROOT)],
            check=False,
        )
        if code == 0 and verified.returncode == 0:
            (output / "classification.json").write_text(
                json.dumps({"kind": "pass", "detail": "begin recovery verified"}) + "\n",
                encoding="utf-8",
            )
            return 0
        (output / "classification.json").write_text(
            json.dumps({"kind": "evidence" if code == 0 else "driver_failure"}) + "\n",
            encoding="utf-8",
        )
        return code or verified.returncode or 1
    except Exception as exc:
        (output / "classification.json").write_text(
            json.dumps({"kind": "readiness_timeout", "detail": str(exc)}) + "\n",
            encoding="utf-8",
        )
        return 1
    finally:
        if child.poll() is None:
            try:
                child.stdin.write(json.dumps({"op": "stop"}) + "\n")
                child.stdin.flush()
            except OSError:
                pass
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.kill(child.pid, signal.SIGTERM)
        log.close()


def _control(
    message: dict[str, Any],
    child: subprocess.Popen[str],
    base: str,
    queue: list[dict[str, Any]],
    lock: threading.Lock,
    integration: Any,
    port: int,
    output: Path,
    server_pid: dict[str, int],
) -> dict[str, Any]:
    operation = message.get("op")
    identifier = message.get("id")
    assert child.stdin is not None
    if operation == "arm":
        child.stdin.write(json.dumps({"op": "arm"}) + "\n")
        child.stdin.flush()
        return {"id": identifier, "ok": True}
    raw = message.get("raw")
    if operation in {"recover-while-blocked", "recover", "replay-begin"} and not isinstance(
        raw, str
    ):
        return {"id": identifier, "ok": False, "error": "request bytes are missing"}
    if operation == "recover-while-blocked":
        if not _wait_for(queue, lock, "prepare-blocked", 20):
            return {"id": identifier, "ok": False, "error": "preparation did not block"}
        status, response = post_raw(base, BEGIN_RECOVERY_PATH, str(raw))
        child.stdin.write(json.dumps({"op": "release"}) + "\n")
        child.stdin.flush()
        return {"id": identifier, "ok": True, "status": status, "response_base64": response}
    if operation == "recover":
        status, response = post_raw(base, BEGIN_RECOVERY_PATH, str(raw))
        return {"id": identifier, "ok": True, "status": status, "response_base64": response}
    if operation == "replay-begin":
        status, response = post_raw(base, BEGIN_REQUEST_PATH, str(raw))
        return {"id": identifier, "ok": True, "status": status, "response_base64": response}
    if operation == "restart":
        previous = server_pid["value"]
        child.stdin.write(json.dumps({"op": "stop"}) + "\n")
        child.stdin.flush()
        child.wait(timeout=5)
        replacement = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--child-server", "--port", str(port)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=(output / "logs" / "server-b.log").open("w", encoding="utf-8"),
            text=True,
        )
        assert replacement.stdout is not None and replacement.stdin is not None
        line = replacement.stdout.readline()
        ready = json.loads(line)
        child.wait = replacement.wait  # type: ignore[method-assign]
        child.stdin = replacement.stdin
        child.kill = replacement.kill  # type: ignore[method-assign]
        server_pid["value"] = int(ready["pid"])
        if not integration.wait_for_http(f"{ready['base']}/lesson-inbox.html", 15):
            return {"id": identifier, "ok": False, "error": "restart was not ready"}
        return {
            "id": identifier,
            "ok": True,
            "pid": ready["pid"],
            "previous_pid": previous,
        }
    return {"id": identifier, "ok": False, "error": f"unknown op {operation}"}


def _wait_for(
    queue: list[dict[str, Any]], lock: threading.Lock, event: str, timeout: float
) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with lock:
            if any(item.get("event") == event for item in queue):
                return True
        time.sleep(0.05)
    return False


if __name__ == "__main__":
    sys.exit(main())
