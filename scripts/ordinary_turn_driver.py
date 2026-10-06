#!/usr/bin/env python3
"""Model-free preparation for ten ordinary persisted turns, separate from Analyze.

No native/configuration/complete-observer adapter is installed by this module.
The CLI writes a blocked four-run manifest only. A reviewed external facility
must admit controller ancestry BEFORE launch and independently measure loss,
connections, short execs, escaped descendants and PID reuse. Hashes are input
bindings, never observer certificates. Local-owner rewriting remains possible.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import math
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import abstention_ledger as ledger

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

CAP = 10
GRANT_SHA256: str | None = None
AUTHORITY_DIR: Path | None = None
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_REVISION = re.compile(r"[a-f0-9]{40}\Z")


class RefusalError(Exception):
    """An admission, binding, accounting, observation or native join is absent."""


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def digest(body: object) -> str:
    return sha(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())


@dataclasses.dataclass(frozen=True)
class Limits:
    seconds: float = 900.0
    output_bytes: int = 4 * 1024 * 1024


@dataclasses.dataclass(frozen=True)
class FileBinding:
    path: str
    sha256: str

    def validate(self) -> None:
        if not Path(self.path).is_absolute() or not _DIGEST.fullmatch(self.sha256):
            raise RefusalError("input file identity must be absolute and digest-bound")
        if sha(Path(self.path).read_bytes()) != self.sha256:
            raise RefusalError("reviewed input file changed")


@dataclasses.dataclass(frozen=True)
class Plan:
    ordinal: int
    session_id: str
    revision: str
    workspace: str
    model: str
    effort: str
    prompt: str
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    files: Mapping[str, FileBinding]
    board_port: int
    transcript_path: str

    def bindings(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "revision": self.revision,
            "workspace": self.workspace,
            "model": self.model,
            "effort": self.effort,
            "argv_sha256": digest(self.argv),
            "environment_sha256": digest(dict(self.environment)),
            "files": {key: dataclasses.asdict(value) for key, value in self.files.items()},
            "board_port": self.board_port,
            "transcript_path": self.transcript_path,
            "reading_mode": "off",
            "expected_cargento_model_calls": 0,
        }

    def campaign(self) -> str:
        bindings = self.bindings()
        bindings["argv_sha256"] = digest(
            ["--owned-session" if arg in ("--session-id", "--resume") else arg for arg in self.argv]
        )
        return digest(bindings)

    def fingerprint(self) -> str:
        return digest(
            {**self.bindings(), "ordinal": self.ordinal, "prompt_sha256": sha(self.prompt.encode())}
        )

    def validate(self) -> None:
        try:
            valid_sid = str(uuid.UUID(self.session_id)) == self.session_id
        except ValueError:
            valid_sid = False
        if not valid_sid or not _REVISION.fullmatch(self.revision):
            raise RefusalError("full native session identity and final revision required")
        if type(self.ordinal) is not int or not 1 <= self.ordinal <= CAP:
            raise RefusalError("ordinary attempt ordinal outside ten-attempt allowance")
        if (
            not self.model
            or not self.effort
            or not self.prompt.strip()
            or len(self.prompt.encode()) > 65536
        ):
            raise RefusalError("reviewed model, effort and bounded exact prompt required")
        if not Path(self.workspace).is_absolute() or not Path(self.workspace).is_dir():
            raise RefusalError("reviewed absolute workspace required")
        if not Path(self.transcript_path).is_absolute():
            raise RefusalError("persisted native transcript path required")
        self.validate_runtime()

    def validate_runtime(self) -> None:
        home = self.environment.get("CARGENTO_HOME", "")
        if not home or not Path(home).is_absolute() or not Path(home).is_dir():
            raise RefusalError("explicit owned CARGENTO_HOME required")
        account = ledger.canonical_home()
        if account is None or Path(home).resolve() == Path(account, ".cargento").resolve():
            raise RefusalError("account/default CARGENTO_HOME cannot protect the owned port")
        if (
            type(self.board_port) is not int
            or not 1024 <= self.board_port <= 65535
            or self.board_port in (4553, 4563, 4567)
        ):
            raise RefusalError("explicit non-owner board port required")
        if set(self.files) != {"cli", "settings", "hooks", "mcp"}:
            raise RefusalError("CLI, settings, hooks and MCP identities required")
        for file in self.files.values():
            file.validate()
        if not self.argv or self.argv[0] != self.files["cli"].path:
            raise RefusalError("argv must invoke the reviewed CLI identity")
        if any(
            arg.split("=", 1)[0] in ("--no-session-persistence", "--safe-mode", "--bare")
            for arg in self.argv
        ):
            raise RefusalError("ordinary turns must preserve native persistence and hooks")
        self.validate_session_arguments()

    def validate_session_arguments(self) -> None:
        session_flags = [arg for arg in self.argv if arg in ("--session-id", "--resume")]
        if not session_flags:
            return  # Local stubs only; real native argv needs configuration admission.
        expected = "--session-id" if self.ordinal == 1 else "--resume"
        if session_flags != [expected]:
            raise RefusalError("native session creation/resume does not match attempt order")
        index = self.argv.index(expected)
        if index + 1 >= len(self.argv) or self.argv[index + 1] != self.session_id:
            raise RefusalError("native argv session identity differs from persisted-session plan")


def claude_arguments(plan: Plan) -> tuple[str, ...]:
    """Prepare help-listed flags only; effective config/persistence remain unverified.

    This does not authorize execution or establish managed/global/plugin
    isolation. The external configuration admission must verify this exact
    command on the installed native version and enforce the reviewed tools.
    """
    return (
        plan.files["cli"].path,
        "--print",
        "--output-format",
        "stream-json",
        "--include-hook-events",
        "--replay-user-messages",
        "--model",
        plan.model,
        "--effort",
        plan.effort,
        "--settings",
        plan.files["settings"].path,
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--mcp-config",
        plan.files["mcp"].path,
        "--session-id" if plan.ordinal == 1 else "--resume",
        plan.session_id,
    )


@dataclasses.dataclass(frozen=True)
class NativeCapture:
    before: bytes
    after: bytes
    hooks: bytes


@dataclasses.dataclass(frozen=True)
class Observation:
    evidence_kind: str
    loss: int
    cargento_model_calls: int
    elapsed_seconds: float
    output_bytes: int
    receipt_sha256: str


class Scope(Protocol):
    def launch(self, plan: Plan, limits: Limits) -> NativeCapture: ...
    def cleanup(self) -> bool: ...
    def close(self) -> Observation: ...


class Adapter(Protocol):
    def admit(self, plan: Plan) -> Scope:
        """Verify runtime configuration and admit controller ancestry before any child."""
        ...


class NativeConfiguration(Protocol):
    def admit(self, plan: Plan) -> None:
        """Review effective native flags, persistence, hooks, MCP and managed/global config.

        Must refuse unknown customizations. A settings-file hash alone cannot
        prove isolation; this reviewed implementation binds actual effective
        model/effort/session/argv/environment to the plan. No implementation is
        installed here and no JSON 'passed' field can substitute for it.
        """
        ...

    def capture(self, plan: Plan) -> NativeCapture: ...


class LaunchAdmission(Protocol):
    def before_native_launch(self, plan: Plan) -> None:
        """Confirm the already admitted controller ancestry and current loss state."""
        ...


class OwnedObservation(LaunchAdmission, Protocol):
    def cleanup(self) -> bool:
        """Reconcile/stop every owned descendant, including escapes and reused PIDs."""
        ...

    def close(self) -> Observation: ...


class CompleteObserver(Protocol):
    def admit_controller(self, pid: int, plan: Plan) -> OwnedObservation:
        """Require independently accepted full exec/flow/ancestry/loss controls first."""
        ...


@dataclasses.dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    seconds: float


def require_charge(plan: Plan, *, claim: bool = False) -> None:
    path = budget_path()
    with ledger.locked(str(path)):
        body = json.loads(path.read_bytes())
        calls = body.get("calls", [])
        if (
            body.get("cap") != CAP
            or body.get("enabled") is not True
            or body.get("requires_complete_owned_observer") is not True
            or len(calls) != plan.ordinal
            or calls[-1].get("status") != "charged"
            or calls[-1].get("inputs_sha256") != plan.fingerprint()
            or calls[-1].get("owner_pid") != os.getpid()
            or calls[-1].get("native_started") is True
        ):
            raise RefusalError("native child requires the exact durable open ordinary charge")
        if claim:
            calls[-1]["native_started"] = True
            write_private(path, body)


class NativeProcess:
    """Bounded local process guard. Group cleanup is only corroborating evidence."""

    complete_descendant_proof = False

    def __init__(self, admission: LaunchAdmission | None = None) -> None:
        self.admission = admission
        self.process: subprocess.Popen[bytes] | None = None
        self.started = False
        self.cleaned = False

    def run(self, plan: Plan, limits: Limits) -> ProcessResult:
        if os.name != "posix":
            raise RefusalError("native process guard requires reviewed POSIX group support")
        if self.started:
            raise RefusalError("native process guard is single-use; no automatic retry")
        self.started = True
        plan.validate()
        require_charge(plan)
        if self.admission is None:
            raise RefusalError("complete owned ancestry admission required before native child")
        self.admission.before_native_launch(plan)
        if (
            not math.isfinite(limits.seconds)
            or not 0 < limits.seconds <= Limits().seconds
            or type(limits.output_bytes) is not int
            or not 0 < limits.output_bytes <= Limits().output_bytes
        ):
            raise RefusalError("native process bounds cannot exceed reviewed limits")
        plan.validate()
        require_charge(plan, claim=True)
        started = time.monotonic()
        self.process = subprocess.Popen(  # noqa: S603 - exact reviewed argv, no shell
            plan.argv,
            cwd=plan.workspace,
            env=dict(plan.environment),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        process = self.process
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RefusalError("native pipes unavailable")
        try:
            return self.read_output(plan, limits, started, process)
        finally:
            self.cleanup()
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()

    def read_output(
        self, plan: Plan, limits: Limits, started: float, process: subprocess.Popen[bytes]
    ) -> ProcessResult:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RefusalError("native pipes unavailable")
        output = {"stdout": bytearray(), "stderr": bytearray()}
        prompt = memoryview(plan.prompt.encode())
        written = 0
        with selectors.DefaultSelector() as selector:
            for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            os.set_blocking(process.stdin.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            while selector.get_map():
                remaining = limits.seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise RefusalError("ordinary native wall-time limit reached")
                for key, _ in selector.select(min(remaining, 0.05)):
                    selected_stream = key.fileobj
                    if key.data == "stdin":
                        written = self.write_prompt(key.fd, prompt, written)
                        if written == len(prompt):
                            selector.unregister(selected_stream)
                            process.stdin.close()
                    else:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(selected_stream)
                        else:
                            output[key.data].extend(chunk)
                            if sum(len(body) for body in output.values()) > limits.output_bytes:
                                raise RefusalError("ordinary aggregate stdout/stderr limit reached")
        code = self.wait_exit(process, limits.seconds - (time.monotonic() - started))
        return ProcessResult(
            code, bytes(output["stdout"]), bytes(output["stderr"]), time.monotonic() - started
        )

    def write_prompt(self, fd: int, prompt: memoryview[int], written: int) -> int:
        try:
            return written + os.write(fd, prompt[written:])
        except BrokenPipeError:
            return len(prompt)

    def wait_exit(self, process: subprocess.Popen[bytes], remaining: float) -> int:
        try:
            code = process.wait(timeout=max(remaining, 0.001))
        except subprocess.TimeoutExpired as error:
            raise RefusalError("ordinary native wall-time limit reached") from error
        if code != 0:
            raise RefusalError("native CLI failed; no uncapped fallback or automatic retry")
        return code

    def cleanup(self) -> bool:
        process = self.process
        if process is None or self.cleaned:
            return True
        # A reaped parent's numeric PGID could be reused. Do not signal it;
        # the independent observer owns exact remaining-descendant cleanup.
        if process.returncode is not None:
            self.cleaned = True
            return True
        # This owned PGID cannot prove escapes/PID reuse. The external scope
        # must independently stop and reconcile those before real acceptance.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            return False
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return False
        self.cleaned = process.returncode is not None
        return self.cleaned


class NativeScope:
    def __init__(self, plan: Plan, config: NativeConfiguration, observer: OwnedObservation) -> None:
        self.fingerprint = plan.fingerprint()
        self.plan = plan
        self.config = config
        self.observer = observer
        self.process = NativeProcess(observer)
        self.result: ProcessResult | None = None
        self.last_capture: NativeCapture | None = None

    def launch(self, plan: Plan, limits: Limits) -> NativeCapture:
        if plan.fingerprint() != self.fingerprint:
            raise RefusalError("admitted plan changed")
        self.config.admit(plan)
        before = self.config.capture(plan)
        self.result = self.process.run(plan, limits)
        after = self.config.capture(plan)
        self.last_capture = after
        if not after.hooks.startswith(before.hooks):
            raise RefusalError("owned hook capture prefix changed")
        return NativeCapture(before.after, after.after, after.hooks[len(before.hooks) :])

    def cleanup(self) -> bool:
        try:
            local = self.process.cleanup()
        finally:
            complete = self.observer.cleanup()
        return local and complete

    def close(self) -> Observation:
        observation = self.observer.close()
        if self.last_capture is not None:
            current = self.config.capture(self.plan)
            if current.after != self.last_capture.after or current.hooks != self.last_capture.hooks:
                raise RefusalError(
                    "native source or hook capture moved during cleanup/observer close"
                )
        if self.result is None:
            return observation
        return dataclasses.replace(
            observation,
            elapsed_seconds=max(observation.elapsed_seconds, self.result.seconds),
            output_bytes=max(
                observation.output_bytes, len(self.result.stdout) + len(self.result.stderr)
            ),
        )


class NativeAdapter:
    def __init__(self, config: NativeConfiguration, observer: CompleteObserver) -> None:
        self.config = config
        self.observer = observer

    def admit(self, plan: Plan) -> NativeScope:
        self.config.admit(plan)
        observer = self.observer.admit_controller(os.getpid(), plan)
        return NativeScope(plan, self.config, observer)


def write_private(path: Path, body: Mapping[str, Any]) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".ordinary-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(body, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        if os.name == "posix":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


def budget_path() -> Path:
    if AUTHORITY_DIR is None or GRANT_SHA256 is None:
        raise RefusalError("external binding to the existing authority and reviewed grant absent")
    if sha((AUTHORITY_DIR / "grant.json").read_bytes()) != GRANT_SHA256:
        raise RefusalError("ordinary allowance does not bind the reviewed current grant")
    return AUTHORITY_DIR / "ordinary-turn-budget.json"


def read_budget() -> dict[str, Any]:
    try:
        body = json.loads(budget_path().read_bytes())
    except (OSError, ValueError) as error:
        raise RefusalError("existing ordinary allowance unreadable; never reset") from error
    if (
        not isinstance(body, dict)
        or type(body.get("cap")) is not int
        or body.get("cap") != CAP
        or body.get("enabled") is not True
        or body.get("requires_complete_owned_observer") is not True
        or not isinstance(body.get("calls"), list)
    ):
        raise RefusalError("ordinary allowance disabled, malformed, or changed")
    calls = body["calls"]
    for ordinal, call in enumerate(calls, 1):
        if (
            not isinstance(call, dict)
            or call.get("ordinal") != ordinal
            or call.get("status") not in ("charged", "held", "synthetic-joined", "native-joined")
            or any(
                not isinstance(call.get(key), str) or not _DIGEST.fullmatch(call[key])
                for key in ("inputs_sha256", "campaign_sha256")
            )
        ):
            raise RefusalError("ordinary attempt history malformed; reviewed recovery required")
    if len(calls) > CAP or any(call["status"] in ("charged", "held") for call in calls):
        raise RefusalError(
            "open ordinary attempt or hold; cleanup/review required, no automatic retry"
        )
    return body


def reserve(plan: Plan) -> None:
    path = budget_path()
    with ledger.locked(str(path)):
        body = read_budget()
        calls = body["calls"]
        if len(calls) >= CAP or plan.ordinal != len(calls) + 1:
            raise RefusalError("ordinary cap/order reached; attempts are never refunded")
        if calls and any(call["campaign_sha256"] != plan.campaign() for call in calls):
            raise RefusalError("one persisted session/configuration required across ordinary turns")
        calls.append(
            {
                "ordinal": plan.ordinal,
                "status": "charged",
                "at": time.time(),
                "owner_pid": os.getpid(),
                "inputs_sha256": plan.fingerprint(),
                "campaign_sha256": plan.campaign(),
                "bindings": plan.bindings(),
                "prompt_sha256": sha(plan.prompt.encode()),
                "real_turn_proof": False,
            }
        )
        write_private(path, body)


def finish(plan: Plan, status: str, receipts: Mapping[str, Any]) -> dict[str, Any]:
    path = budget_path()
    with ledger.locked(str(path)):
        body = json.loads(path.read_bytes())
        call = body["calls"][plan.ordinal - 1]
        if call["status"] != "charged" or call["inputs_sha256"] != plan.fingerprint():
            raise RefusalError("charged attempt changed before completion; leave open")
        call.update(status=status, **receipts)
        try:
            write_private(path, body)
        except BaseException:
            # Replacement may have published completion before directory fsync failed.
            # A persistent filesystem failure can defeat this hold too; never refund.
            call.update(status="held", real_turn_proof=False, completion_uncertain=True)
            with contextlib.suppress(BaseException):
                write_private(path, body)
            raise
        return dict(call)


def rows(body: bytes) -> list[dict[str, Any]]:
    try:
        records = [json.loads(line) for line in body.splitlines() if line.strip()]
    except ValueError as error:
        raise RefusalError("native capture contains invalid JSON") from error
    if not all(isinstance(record, dict) for record in records):
        raise RefusalError("native capture contains non-record values")
    return records


def verify_native_prefix(plan: Plan, capture: NativeCapture) -> None:
    if capture.before and not capture.before.endswith(b"\n"):
        raise RefusalError("native prefix is not a complete recorded boundary")
    previous = rows(capture.before)
    if plan.ordinal == 1:
        if any(row.get("type") in ("user", "assistant") for row in previous):
            raise RefusalError("fresh native session already has person/agent messages")
    else:
        history = json.loads(budget_path().read_bytes())["calls"]
        if len(history) < plan.ordinal - 1 or history[plan.ordinal - 2].get("after_sha256") != sha(
            capture.before
        ):
            raise RefusalError("resumed native source does not extend the last verified prefix")
    if not capture.after.startswith(capture.before):
        raise RefusalError("persisted source prefix was rewritten")


def validate_native_identities(
    plan: Plan, capture: NativeCapture, messages: Sequence[dict[str, Any]]
) -> None:
    if not messages:
        raise RefusalError("new native messages do not join the owned parent session")
    prior_ids = {
        row["uuid"]
        for row in rows(capture.before)
        if isinstance(row.get("uuid"), str) and row["uuid"]
    }
    seen = prior_ids.copy()
    for row in messages:
        identity = row.get("uuid")
        message = row.get("message")
        if (
            row.get("sessionId") != plan.session_id
            or row.get("isSidechain")
            or row.get("isMeta")
            or row.get("agentId")
            or not isinstance(message, dict)
            or message.get("role") != row["type"]
            or not isinstance(identity, str)
            or not identity.strip()
            or identity in seen
        ):
            raise RefusalError("native parent identity, role or UUID is ambiguous or ineligible")
        seen.add(identity)


def native_join(plan: Plan, capture: NativeCapture) -> dict[str, str]:
    verify_native_prefix(plan, capture)
    added = rows(capture.after[len(capture.before) :])
    messages = [row for row in added if row.get("type") in ("user", "assistant")]
    validate_native_identities(plan, capture, messages)
    users = [
        row
        for row in messages
        if row["type"] == "user"
        and row.get("message", {}).get("role") == "user"
        and not row.get("isMeta")
    ]
    # Native tool-result user records are not ordinary person messages.
    users = [
        row
        for row in users
        if not isinstance(row.get("message", {}).get("content"), list)
        or not any(
            item.get("type") == "tool_result"
            for item in row["message"]["content"]
            if isinstance(item, dict)
        )
    ]
    if len(users) != 1 or users[0]["message"].get("content") != plan.prompt:
        raise RefusalError("one exact native person prompt required")
    if messages[0] is not users[0]:
        raise RefusalError("added native messages precede the new person anchor")
    user_id = users[0].get("uuid")
    known = {user_id}
    final: dict[str, Any] | None = None
    for row in messages[messages.index(users[0]) + 1 :]:
        identity = row.get("uuid")
        if not isinstance(identity, str) or identity in known or row.get("parentUuid") not in known:
            raise RefusalError("native parent/UUID chain is ambiguous or unrelated")
        known.add(identity)
        if row["type"] == "assistant":
            final = row
    if (
        not isinstance(user_id, str)
        or final is None
        or final.get("message", {}).get("stop_reason") != "end_turn"
        or final is not messages[-1]
    ):
        raise RefusalError("newest owned native reply lacks explicit end_turn")
    hooks = rows(capture.hooks)
    joined = [row for row in hooks if row.get("hook_event_name") in ("UserPromptSubmit", "Stop")]
    if (
        [row["hook_event_name"] for row in joined] != ["UserPromptSubmit", "Stop"]
        or any(
            row.get("session_id") != plan.session_id
            or row.get("cwd") != plan.workspace
            or row.get("transcript_path") != plan.transcript_path
            for row in joined
        )
        or joined[0].get("prompt") != plan.prompt
    ):
        raise RefusalError("native person/end_turn and scoped Submit/Stop hooks do not join")
    return {
        "before_sha256": sha(capture.before),
        "after_sha256": sha(capture.after),
        "hooks_sha256": sha(capture.hooks),
        "native_user_uuid": user_id,
        "native_final_uuid": final["uuid"],
    }


def check_observation(cleaned: bool, observation: Observation) -> None:
    if (
        cleaned is not True
        or type(observation.loss) is not int
        or observation.loss != 0
        or type(observation.cargento_model_calls) is not int
        or observation.cargento_model_calls != 0
        or isinstance(observation.elapsed_seconds, bool)
        or not math.isfinite(observation.elapsed_seconds)
        or not 0 <= observation.elapsed_seconds <= Limits().seconds
        or type(observation.output_bytes) is not int
        or not 0 <= observation.output_bytes <= Limits().output_bytes
        or not _DIGEST.fullmatch(observation.receipt_sha256)
        or observation.evidence_kind
        not in ("synthetic-control-only", "independently-admitted-native")
    ):
        raise RefusalError("observer loss, cleanup, limits or model-off accounting incomplete")


def close_scope(
    scope: Scope, receipts: dict[str, Any], error: BaseException | None
) -> BaseException | None:
    cleaned = False
    try:
        cleaned = scope.cleanup()
    except BaseException as caught:  # noqa: BLE001 - preserve interruption and still close observer
        if error is None:
            error = caught
    try:
        observation = scope.close()
        receipts.update(cleaned=cleaned, observation=dataclasses.asdict(observation))
        check_observation(cleaned, observation)
    except BaseException as caught:  # noqa: BLE001 - all errors leave the durable charge held
        if error is None:
            error = caught
    return error


def run_turn(plan: Plan, adapter: Adapter | None = None) -> dict[str, Any]:
    plan.validate()
    read_budget()  # Disabled allowance refuses without even creating a lock file.
    if adapter is None:
        raise RefusalError(
            "reviewed native configuration and complete owned observer adapter absent"
        )
    scope = adapter.admit(plan)
    charged = False
    error: BaseException | None = None
    receipts: dict[str, Any] = {"real_turn_proof": False}
    try:
        reserve(plan)
        charged = True
        plan.validate()
        capture = scope.launch(plan, Limits())
        receipts.update(native_join(plan, capture))
    except BaseException as caught:  # noqa: BLE001 - cleanup and held charge also cover interruptions
        error = caught
    finally:
        error = close_scope(scope, receipts, error)
    if charged:
        kind = receipts.get("observation", {}).get("evidence_kind")
        status = (
            "held"
            if error
            else "synthetic-joined"
            if kind == "synthetic-control-only"
            else "native-joined"
        )
        receipts["real_turn_proof"] = error is None and kind == "independently-admitted-native"
        try:
            result = finish(plan, status, receipts)
        except BaseException as caught:  # noqa: BLE001 - cleanup and held charge also cover interruptions
            if error is None:
                error = caught
    if error is not None:
        raise error
    return result


def manifest(revision: str) -> dict[str, Any]:
    if not _REVISION.fullmatch(revision):
        raise RefusalError("one final forty-character revision required")
    required = [
        "owned_scope_admission",
        "loss_and_cleanup_receipts",
        "native_session_and_hooks",
        "outbound_process_attribution",
        "page_network_export",
        "copy_readback",
        "transcript_before_after",
    ]
    return {
        "v": 1,
        "revision": revision,
        "ordinary_attempt_cap": CAP,
        "allowance_transfer": False,
        "real_readiness": False,
        "complete_owned_observer": "external-required",
        "runs": [
            {
                "run_id": str(uuid.uuid4()),
                "kind": kind,
                "status": "blocked",
                "expected_cargento_model_calls": None if kind == "default" else 0,
                "expected_ordinary_turns": CAP if kind == "monitor" else 0,
                "model_consent": "fresh-allow"
                if kind == "default"
                else "off"
                if kind == "monitor"
                else "declined"
                if kind == "declined"
                else "unavailable",
                "bindings": dict.fromkeys(
                    (
                        "session_id",
                        "route",
                        "model",
                        "effort",
                        "prompt_sha256",
                        "cli_version",
                        "cli_sha256",
                        "settings_sha256",
                        "hooks_sha256",
                        "mcp_sha256",
                        "environment_sha256",
                        "workspace",
                        "owned_board_port",
                        "owned_home",
                        "owned_tab",
                        "native_configuration_admission",
                        "independent_observer_acceptance",
                    )
                ),
                "required_artifacts": required,
                "unreachable": [],
            }
            for kind in ("default", "monitor", "no-harness", "declined")
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--manifest-out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.manifest_out.exists():
        parser.error("manifest destination already exists; never overwrite an authority or receipt")
    write_private(args.manifest_out, manifest(args.revision))
    print("Prepared blocked four-run manifest; no native launch or authority write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
