"""Integration witness for a received lesson, including a real process restart.

The positional output is the evidence directory. ``--child-server`` is an
internal mode: this script starts it, and it is not a production entry point.
Browser launch uses ``--chrome-executable`` and ``--puppeteer-module``, or
``DO016_CHROME_EXECUTABLE`` and ``DO016_PUPPETEER_MODULE``. The Linux defaults
remain the paths below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.lesson_delivery_api import (
    LESSON_DELIVERY_API_PREFIX,
    LocalLessonDeliveryApi,
)
from master_all_strings.mvp.local_server import serve_mvp_directory

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "resources" / "lesson" / "examples" / "local_midi_basic.json"
CAPTURE = ROOT / "web" / "mvp1" / "tests" / "do016_integration_capture.mjs"
VERIFIER = ROOT / "scripts" / "verify_do016_integration_evidence.py"
TITLE = "Stage 9 Integration Etude"
DELIVERY_ID = "delivery-stage9"
TEMPO_BPM = 8.0
CHROME_ENV = "DO016_CHROME_EXECUTABLE"
PUPPETEER_ENV = "DO016_PUPPETEER_MODULE"
DEFAULT_CHROME = Path("/usr/local/bin/google-chrome")
DEFAULT_PUPPETEER = Path(
    "/tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js"
)
FROZEN_DIR = Path("docs/mvp2/do015_artifacts")


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


def node_modules_dir(puppeteer_path: Path) -> str:
    for parent in puppeteer_path.parents:
        if parent.name == "node_modules":
            return str(parent)
    return str(puppeteer_path.parent)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def central_now() -> str:
    return datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%dT%H:%M:%S %Z")


def wait_for_http(url: str, timeout: float) -> bool:
    """Poll until ``url`` answers 200 or the deadline passes."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))
    return False


def terminate_process(proc: subprocess.Popen[Any], timeout: float) -> None:
    """Stop one process this witness started. Other processes are left alone."""

    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)


def stop_child(proc: subprocess.Popen[Any], timeout: float = 5) -> None:
    """Ask a child server to close, then terminate it if it does not."""

    if proc.poll() is not None:
        return
    if proc.stdin is not None and not proc.stdin.closed:
        try:
            proc.stdin.write('{"op":"stop"}\n')
            proc.stdin.flush()
        except (OSError, ValueError):
            pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_process(proc, timeout)


def write_classification(output: Path, kind: str, detail: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    payload = {"kind": kind, "detail": detail, "at": utc_now()}
    (output / "classification.json").write_text(json.dumps(payload, indent=2) + "\n",
        encoding="utf-8")


def custom_assignment() -> object:
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw["identity"]["title"] = TITLE
    raw["musical_content"]["tempo_changes"][0]["tempo_bpm"] = TEMPO_BPM
    raw["instruction"]["objective"] = "Show one received lesson from inbox through feedback."
    raw["instruction"]["teacher_note"] = "Integration witness assignment. Not a bundled demo."
    return deserialize_lesson_assignment(json.dumps(raw))


def _request(base: str, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int,
    dict[str, Any]]:
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
            parsed = json.loads(payload or b"{}")
            return response.status, parsed if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            parsed = json.loads(payload or b"{}")
        except json.JSONDecodeError:
            parsed = {}
        return exc.code, parsed if isinstance(parsed, dict) else {}


def receive_delivery(base: str, assignment: object, delivery_id: str) -> tuple[int, dict[str, Any]]:
    return _request(
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


def delivery_count(base: str) -> int:
    status, body = _request(base, "GET", LESSON_DELIVERY_API_PREFIX)
    if status != 200:
        raise RuntimeError(f"delivery list failed: {status} {body}")
    count = body.get("count")
    if not isinstance(count, int):
        raise RuntimeError(f"delivery list has no count: {body}")
    return count


def frozen_hashes(root: Path) -> list[dict[str, str]]:
    records = []
    directory = root / FROZEN_DIR
    for path in sorted(directory.glob("*")):
        if not path.is_file():
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return records


def git_text(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def command_text(command: list[str]) -> str:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return (completed.stdout or completed.stderr).strip()


def run_child(port: int) -> int:
    """Serve one fresh inbox on ``port``. The parent owns this process."""

    from http.server import ThreadingHTTPServer

    ThreadingHTTPServer.allow_reuse_address = True
    server = None
    last_error = "the port did not bind"
    for _ in range(50):
        try:
            server, _thread, url = serve_mvp_directory(
                ROOT / "web" / "mvp1",
                host="127.0.0.1",
                port=port,
                open_browser=False,
                path="/lesson-inbox.html",
                lesson_delivery_api=LocalLessonDeliveryApi(),
            )
            break
        except OSError as exc:
            last_error = str(exc)
            time.sleep(0.1)
    if server is None:
        print(last_error, file=sys.stderr)
        return 1
    base = url.rsplit("/", 1)[0]
    sys.stdout.write(json.dumps({"event": "listening", "base": base, "pid": os.getpid()}) + "\n")
    sys.stdout.flush()
    try:
        for line in sys.stdin:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("op") == "stop":
                break
    finally:
        server.shutdown()
        server.server_close()
    return 0


class Harness:
    """Child servers, their epochs, and the barriers the browser waits on."""

    def __init__(self, output: Path, assignment: object) -> None:
        self.output = output
        self.assignment = assignment
        self.port = 0
        self.proc: subprocess.Popen[str] | None = None
        self.base = ""
        self.epochs: list[dict[str, Any]] = []
        self.barriers: list[dict[str, Any]] = []
        self._names = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        self._stderr: Any = None

    def start_epoch(self, timeout: float = 15) -> dict[str, Any]:
        name = next(self._names)
        if self.port == 0:
            self.port = free_port()
        log_dir = self.output / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stderr = (log_dir / f"epoch-{name}.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--child-server", "--port",
                str(self.port)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
        )
        assert proc.stdout is not None
        line = proc.stdout.readline()
        threading.Thread(target=_drain, args=(proc.stdout, stderr), daemon=True).start()
        if proc.poll() is not None or not line:
            stderr.write(f"child exited {proc.returncode} before listening\n")
            stderr.close()
            raise RuntimeError(f"epoch {name} exited before it listened")
        ready = json.loads(line)
        base = str(ready["base"])
        if not wait_for_http(f"{base}/lesson-inbox.html", timeout):
            stop_child(proc)
            stderr.close()
            raise RuntimeError(f"epoch {name} did not answer HTTP")
        pid = int(ready["pid"])
        epoch = {
            "name": name,
            "pid": pid,
            "base": base,
            "ready": True,
            "started_at": utc_now(),
            "delivery_count_at_ready": delivery_count(base),
        }
        self.proc = proc
        self.base = base
        self._stderr = stderr
        self.epochs.append(epoch)
        return epoch

    def stop_current(self) -> None:
        proc = self.proc
        if proc is None:
            return
        stop_child(proc)
        self.proc = None
        if self.epochs:
            self.epochs[-1]["stopped_at"] = utc_now()
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    def restart(self) -> dict[str, Any]:
        if not self.epochs:
            raise RuntimeError("restart needs a running epoch")
        previous = self.epochs[-1]
        self.stop_current()
        epoch = self.start_epoch()
        barrier = {
            "op": "restart",
            "ok": True,
            "epoch_before": previous["name"],
            "epoch_after": epoch["name"],
            "previous_pid": previous["pid"],
            "pid": epoch["pid"],
            "at": utc_now(),
        }
        self.barriers.append(barrier)
        return barrier

    def reseed(self) -> dict[str, Any]:
        status, body = receive_delivery(self.base, self.assignment, DELIVERY_ID)
        if status != 201:
            raise RuntimeError(f"reseed failed: {status} {body}")
        barrier = {
            "op": "reseed",
            "ok": True,
            "epoch": self.epochs[-1]["name"],
            "pid": self.epochs[-1]["pid"],
            "status": status,
            "delivery_id": DELIVERY_ID,
            "delivery_count": delivery_count(self.base),
            "at": utc_now(),
        }
        self.barriers.append(barrier)
        return barrier

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        identifier = message.get("id")
        try:
            operation = message.get("op")
            if operation == "restart":
                payload = self.restart()
            elif operation == "reseed":
                payload = self.reseed()
            elif operation == "epoch":
                current = self.epochs[-1]
                payload = {"ok": True, "epoch": current["name"], "pid": current["pid"],
                    "base": self.base}
            else:
                payload = {"ok": False, "error": f"unknown barrier {operation}"}
        except Exception as exc:
            payload = {"ok": False, "error": str(exc)}
        return {"id": identifier, **payload}

    def close(self) -> None:
        self.stop_current()


def _drain(pipe: Any, sink: Any) -> None:
    try:
        for line in pipe:
            sink.write(line)
    except (OSError, ValueError):
        return


def _control_loop(sock: socket.socket, harness: Harness, driver: subprocess.Popen[Any]) -> None:
    sock.settimeout(60)
    try:
        connection, _address = sock.accept()
    except OSError:
        return
    with connection:
        connection.settimeout(1)
        pending = b""
        while driver.poll() is None or pending:
            try:
                chunk = connection.recv(65536)
            except TimeoutError:
                if driver.poll() is not None and not pending:
                    break
                continue
            except OSError:
                break
            if not chunk:
                break
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("barrier message is not an object")
                    reply = harness.handle(message)
                except Exception as exc:
                    reply = {"id": None, "ok": False, "error": str(exc)}
                connection.sendall((json.dumps(reply) + "\n").encode())


def run_command_and_reap(
    command: list[str],
    proc: subprocess.Popen[Any],
    output: Path,
    timeout: float,
) -> int:
    """Run ``command`` and always stop ``proc``. A non-zero exit is classified."""

    output.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(command, timeout=timeout, check=False, capture_output=True,
            text=True)
        code = completed.returncode
        (output / "driver.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        code = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        (output / "driver.log").write_text(stdout + stderr, encoding="utf-8")
        write_classification(output, "driver_failure", "the driver timed out")
    finally:
        stop_child(proc, timeout=2)
    if code != 0 and not (output / "classification.json").exists():
        write_classification(output, "driver_failure", f"driver exit {code}")
    return code


def _merge_packet(
    output: Path,
    harness: Harness,
    browser: dict[str, Any],
    *,
    tested_sha: str,
    tested_tree: str,
    dirty: str,
    python_version: str,
    node_version: str,
    chrome_version: str,
    before: list[dict[str, str]],
    after: list[dict[str, str]],
) -> dict[str, Any]:
    after_by_path = {item["path"]: item["sha256"] for item in after}
    frozen = []
    for item in before:
        frozen.append(
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "before_sha256": item["sha256"],
                "after_sha256": after_by_path.get(item["path"], ""),
            }
        )
    packet = {
        "schema": "master_all_strings.do016_integration_evidence",
        "schema_version": "1",
        "run_id": browser.get("run_id"),
        "started_at": browser.get("started_at"),
        "started_at_central": browser.get("started_at_central"),
        "tested_sha": tested_sha,
        "tested_tree": tested_tree,
        "dirty": dirty,
        "python": python_version,
        "node": node_version or browser.get("node"),
        "browser": browser.get("browser"),
        "chrome": chrome_version,
        "os": browser.get("os"),
        "launch": browser.get("launch"),
        "injected_midi": True,
        "physical_midi": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
        "physical_audio": "UNVERIFIED_AUDIO_OUTPUT",
        "custom_assignment": {
            "title": TITLE,
            "delivery_id": DELIVERY_ID,
            "tempo_bpm": TEMPO_BPM,
        },
        "complete": browser.get("complete") is True,
        "failures": browser.get("failures"),
        "notes": browser.get("notes", []),
        "scenarios": browser.get("scenarios", {}),
        "exchanges": browser.get("exchanges", []),
        "epochs": harness.epochs,
        "barriers": harness.barriers,
        "frozen_files": frozen,
        "lost_begin_limitation": (
            "An unconfirmed begin is not repeated. The server may still hold that attempt "
            "until the process exits. This witness does not repair that limitation."
        ),
    }
    (output / "evidence.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    return packet


def run_witness(output: Path, chrome: Path, puppeteer: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    (output / "logs").mkdir(exist_ok=True)
    assignment = custom_assignment()
    harness = Harness(output, assignment)
    tested_sha = git_text("rev-parse", "HEAD")
    tested_tree = git_text("rev-parse", "HEAD^{tree}")
    dirty = git_text("status", "--porcelain")
    before = frozen_hashes(ROOT)
    driver: subprocess.Popen[Any] | None = None
    sock: socket.socket | None = None
    log_handle: Any = None
    code = 1
    kind = "driver_failure"
    detail = "the witness did not finish"
    try:
        epoch = harness.start_epoch()
        status, body = receive_delivery(harness.base, assignment, DELIVERY_ID)
        if status != 201:
            raise RuntimeError(f"receive failed: {status} {body}")
        harness.barriers.append(
            {
                "op": "receive",
                "ok": True,
                "epoch": epoch["name"],
                "pid": epoch["pid"],
                "status": status,
                "delivery_id": DELIVERY_ID,
                "at": utc_now(),
            }
        )
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        control_port = int(sock.getsockname()[1])
        sock.listen(1)
        launch = {
            "base": harness.base,
            "delivery_id": DELIVERY_ID,
            "title": TITLE,
            "chrome_executable": str(chrome),
            "puppeteer_module": str(puppeteer),
            "control_port": control_port,
            "output": str(output),
        }
        (output / "launch.json").write_text(json.dumps(launch, indent=2) + "\n", encoding="utf-8")
        env = os.environ.copy()
        env[CHROME_ENV] = str(chrome)
        env[PUPPETEER_ENV] = str(puppeteer)
        node_path = env.get("NODE_PATH", "")
        modules = node_modules_dir(puppeteer)
        env["NODE_PATH"] = modules if not node_path else os.pathsep.join((modules, node_path))
        log_handle = (output / "logs" / "driver.log").open("w", encoding="utf-8")
        driver = subprocess.Popen(
            ["node", str(CAPTURE), str(output / "launch.json")],
            cwd=ROOT,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        thread = threading.Thread(target=_control_loop, args=(sock, harness, driver), daemon=True)
        thread.start()
        try:
            code = driver.wait(timeout=300)
        except subprocess.TimeoutExpired:
            os.killpg(driver.pid, signal.SIGTERM)
            try:
                driver.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(driver.pid, signal.SIGKILL)
                driver.wait(timeout=5)
            code = 124
            kind = "driver_failure"
            detail = "the browser driver timed out"
        thread.join(timeout=2)
        if code != 0 and kind == "driver_failure" and detail == "the witness did not finish":
            detail = f"browser driver exit {code}"
        browser_path = output / "browser_evidence.json"
        if not browser_path.is_file():
            kind = "driver_failure"
            detail = "the browser driver wrote no evidence"
            code = code or 1
            return code
        browser = json.loads(browser_path.read_text(encoding="utf-8"))
        after = frozen_hashes(ROOT)
        packet = _merge_packet(
            output,
            harness,
            browser,
            tested_sha=tested_sha,
            tested_tree=tested_tree,
            dirty=dirty,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            node_version=command_text(["node", "--version"]),
            chrome_version=command_text([str(chrome), "--version"]),
            before=before,
            after=after,
        )
        (output / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": packet["run_id"],
                    "tested_sha": tested_sha,
                    "tested_tree": tested_tree,
                    "evidence": "evidence.json",
                    "title": TITLE,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        verify = subprocess.run(
            [sys.executable, str(VERIFIER), str(output / "evidence.json"), "--root", str(ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        (output / "logs" / "verifier.log").write_text(verify.stdout + verify.stderr,
            encoding="utf-8")
        if code == 0 and verify.returncode == 0:
            kind = "pass"
            detail = "integration scenarios verified"
            return 0
        if verify.returncode != 0:
            kind = "evidence"
            detail = verify.stdout.strip() or "evidence verifier failed"
        return code or verify.returncode or 1
    except RuntimeError as exc:
        message = str(exc)
        kind = "restart_failure" if "reseed" in message else "readiness_timeout"
        detail = message
        return 1
    finally:
        if sock is not None:
            sock.close()
        harness.close()
        if driver is not None and driver.poll() is None:
            try:
                os.killpg(driver.pid, signal.SIGTERM)
            except OSError:
                terminate_process(driver, 2)
        if log_handle is not None:
            log_handle.close()
        write_classification(output, kind, detail)


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
        parser.error("output directory is required")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        chrome, puppeteer = resolve_browser_config(args.chrome_executable, args.puppeteer_module)
    except BrowserConfigError as exc:
        write_classification(args.output, "browser_launch", str(exc))
        return 2
    return run_witness(args.output, chrome, puppeteer)


if __name__ == "__main__":
    sys.exit(main())
