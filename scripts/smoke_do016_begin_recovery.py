"""Browser witness for keyed Begin recovery.

The child server is a normal local server. The only test hook is a monkeypatch
of preparation inside this process, released by a message on stdin.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "web" / "mvp1" / "tests" / "do016_begin_recovery_capture.mjs"
VERIFIER = ROOT / "scripts" / "verify_do016_begin_recovery_evidence.py"


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
    try:
        if child.poll() is not None or not ready_line:
            raise RuntimeError("child exited before listening")
        ready = json.loads(ready_line)
        base = str(ready["base"])
        if not integration.wait_for_http(f"{base}/lesson-inbox.html", 15):
            raise RuntimeError("child did not answer HTTP")
        assignment = integration.custom_assignment()
        status, _body = integration.receive_delivery(base, assignment, integration.DELIVERY_ID)
        if status != 201:
            raise RuntimeError(f"receive failed: {status}")
        launch = {
            "base": base,
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
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if not line.strip():
                            continue
                        reply = _control(
                            json.loads(line), child, base, queue, lock, integration, port, output
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
            "schema_version": "1",
            "complete": browser.get("complete") is True and code == 0,
            "failures": browser.get("failures"),
            "scenarios": browser.get("scenarios"),
            "exchanges": browser.get("exchanges"),
            "epochs": browser.get("epochs"),
            "notes": browser.get("notes"),
            "tested_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "tested_tree": subprocess.check_output(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
            ).strip(),
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
) -> dict[str, Any]:
    operation = message.get("op")
    identifier = message.get("id")
    assert child.stdin is not None
    if operation == "arm":
        child.stdin.write(json.dumps({"op": "arm"}) + "\n")
        child.stdin.flush()
        return {"id": identifier, "ok": True}
    if operation == "recover-while-blocked":
        body = message.get("body")
        if not _wait_for(queue, lock, "prepare-blocked", 20):
            return {"id": identifier, "ok": False, "error": "preparation did not block"}
        status, response = integration._request(
            base,
            "POST",
            "/api/education/lesson-practice-begin-recoveries",
            body if isinstance(body, dict) else {},
        )
        child.stdin.write(json.dumps({"op": "release"}) + "\n")
        child.stdin.flush()
        return {"id": identifier, "ok": True, "status": status, "response": response}
    if operation == "recover":
        status, response = integration._request(
            base,
            "POST",
            "/api/education/lesson-practice-begin-recoveries",
            message.get("body") if isinstance(message.get("body"), dict) else {},
        )
        return {"id": identifier, "ok": True, "status": status, "response": response}
    if operation == "replay-begin":
        status, response = integration._request(
            base,
            "POST",
            "/api/education/lesson-practice-begin-requests",
            message.get("body") if isinstance(message.get("body"), dict) else {},
        )
        return {"id": identifier, "ok": True, "status": status, "response": response}
    if operation == "restart":
        previous = child.pid
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
        child._pid = replacement.pid  # noqa: SLF001
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
