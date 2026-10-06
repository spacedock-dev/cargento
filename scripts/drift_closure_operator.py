"""Serial native closure observations, frozen sources and reviewed acceptance.

This operator has no grant, activation, migration, refund or provider shortcut.
Its private journal holds lineage and digests; native read files own actual replies.
"""

# ruff: noqa: INP001, SLF001, TRY301 - operator joins the existing bounded native artifact APIs
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import abstention_ledger as authority
import analyze_campaign as campaigns
import drift_closure_grading as grading
import drift_replay as replay
import drift_study_controls as controls
import levels_cases as level_cases


def _bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise authority.LedgerError("A frozen private artifact is missing or exceeds its bound")
    return path.read_bytes()


def _sha(path: Path) -> str:
    return hashlib.sha256(_bytes(path)).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(_bytes(path))


def native_code_binding() -> dict[str, Any]:
    """Actual implementation bytes and checkout identity, without authority claims."""
    root = Path(__file__).resolve().parent.parent
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()  # noqa: S607 - fixed read-only repository query
    return {
        "commit": commit,
        "files": {name: _sha(root / name) for name in grading.NATIVE_CODE_FILES},
    }


class NativeClosureOperator:
    """Prepare existing authority, execute one native row, grade, then pause for review."""

    def __init__(
        self,
        *,
        protocol_path: Path,
        registrations_path: Path,
        blind_path: Path,
        protected_path: Path,
    ) -> None:
        self.campaign = campaigns.Campaign()
        if not campaigns.REPLAY_PATH or os.path.realpath(replay.LEDGER_PATH) != os.path.realpath(
            campaigns.REPLAY_PATH
        ):
            raise authority.LedgerError("Native closure must use the canonical replay ledger")
        ledger_path = Path(campaigns.REPLAY_PATH)
        self.home = ledger_path.parent.parent
        self.paths = replay._paths(str(self.home))
        if ledger_path.parent.resolve() != Path(self.paths["dir"]).resolve():
            raise authority.LedgerError(
                "The canonical ledger does not own the native replay directory"
            )
        self.folder = ledger_path.parent / "closure-operator"
        self.journal_path = self.folder / "journal.json"
        self.frozen_paths = {
            "protocol": Path(protocol_path),
            "registrations": Path(registrations_path),
            "blind": Path(blind_path),
            "protected": Path(protected_path),
        }
        self.frozen = {key: _bytes(path) for key, path in self.frozen_paths.items()}
        self.expected = {
            key: hashlib.sha256(value).hexdigest() for key, value in self.frozen.items()
        }
        self.protocol = json.loads(self.frozen["protocol"])
        self.registrations = json.loads(self.frozen["registrations"])
        self.reading = replay._runtime()[-1]
        if self.folder.is_symlink():
            raise authority.LedgerError("Private native evidence directory cannot be a symlink")
        with authority.locked(str(self.journal_path)):
            state = self._campaign_state()
            self._validate_preparation()
            journal = self._journal(state)
            if journal["attempts"]:
                self._grade(journal)
                self._campaign_state()

    def _context(self) -> dict[str, Any]:
        manifest = self.campaign.manifest
        return {
            "manifest_digest": self.campaign.binding,
            "protocol": manifest["protocols"]["replay"],
            "binding": manifest["bindings"]["replay"],
            "evidence": manifest["evidence"]["replay"],
        }

    def _validate_preparation(self) -> None:
        try:
            self._preflight()
        except (
            ValueError,
            KeyError,
            TypeError,
            OSError,
            RuntimeError,
            authority.LedgerError,
        ) as error:
            if any(call["lane"] == "replay" for call in self.campaign._state()["calls"]):
                self._coverage_stop()
            raise ValueError("Actual frozen preparation is unavailable") from error

    def _preflight(self) -> None:  # noqa: C901, PLR0912, PLR0915 - exact source admission precedes any charge
        if any(_sha(path) != self.expected[key] for key, path in self.frozen_paths.items()):
            raise ValueError("Frozen preparation bytes changed")
        current = campaigns.Campaign()
        if current.manifest != self.campaign.manifest or current.binding != self.campaign.binding:
            raise authority.LedgerError("Reviewed canonical authority changed")
        if (
            self.protocol["input_digest_bindings"].get("native_code_binding")
            != native_code_binding()
        ):
            raise ValueError("Actual native implementation bytes/checkout are not frozen")
        report = self._score({}, [], final=False)
        # Partial grades defer future comparisons; missing source admission is already
        # known and cannot justify spending the opening pilot before that comparison.
        protected = json.loads(self.frozen["protected"])["rows"]
        if any(row.get("admissibility", "unknown") != "admitted" for row in protected):
            raise ValueError("Required protected sources lack independent admission")
        if (
            self.expected["protocol"] != self._context()["binding"]
            or report["evidence"] != self._context()["evidence"]
            or [r["slot"] for r in self.registrations] != self.campaign.manifest["slots"]["replay"]
        ):
            raise ValueError("Frozen source, scorer, marks or slots differ from reviewed authority")
        from cargento_runtime.web import page  # noqa: PLC0415 - actual shipped projection

        projection = grading.digest(
            {
                "node": _sha(Path(replay._ROOT) / "scripts/drift_page.js"),
                "script": grading.digest(page.load_script()),
            }
        )
        if self.protocol["input_digest_bindings"].get("native_page_projection") != projection:
            raise ValueError("The shipped Node/page projection is not frozen")
        native_sources = self.protocol["input_digest_bindings"].get("native_source_files")
        if not isinstance(native_sources, dict) or not native_sources:
            raise ValueError("Complete actual native sources were not preregistered")
        for name, digest in native_sources.items():
            path = Path(name)
            if str(path.resolve()) != name or _sha(path) != digest:
                raise ValueError("An actual native source differs from preregistration")
        body = _json(Path(self.paths["cases"]))
        current_path = Path(self.paths["current"])
        if (
            _sha(current_path)
            != self.protocol["critical_input_binding"]["current_intents_file_sha256"]
        ):
            raise ValueError("The actual original saved intents source changed")
        by_case = {case["id"]: case for case in body["cases"]}
        if len(by_case) != len(body["cases"]):
            raise ValueError("Native case identities are ambiguous")
        required = {str(Path(self.paths["cases"]).resolve()), str(current_path.resolve())}
        saved = _json(current_path).get("intents") or {}
        critical_sources = {
            (s["case"], s["arm"]): s for s in self.protocol["critical_input_binding"]["cases"]
        }
        if len(critical_sources) != len(self.protocol["critical_input_binding"]["cases"]):
            raise ValueError("Critical original source joins are ambiguous")
        predicates = self.protocol["threshold_proposal"]["critical_exact_predicates"]
        checked: dict[tuple[str, str], Any] = {}
        control_sources: dict[str, Any] = {}
        measured: dict[str, Any] = {}
        for reg in self.registrations:
            row = reg["row"]
            case = by_case.get(row["case"])
            if not case:
                raise ValueError("A registered row has no actual native case")
            source = Path(
                replay._transcript(str(case["sid"]), str(body.get("source") or "fixtures"))
            )
            annotation = Path(replay.ANNOTATIONS) / str(case["sid"]) / "annotation.md"
            required.update((str(source.resolve()), str(annotation.resolve())))
            identity = (row["case"], row["arm"])
            if identity not in checked:
                actual = replay.intents(
                    case, replay.conversation(str(source)), _bytes(annotation).decode(), saved
                )
                matched = [intent.revision() for intent in actual if intent.arm == row["arm"]]
                checked[identity] = matched
            if checked[identity] != [reg["intent"]]:
                raise ValueError("Original native source/revision join is missing")
            critical = critical_sources.get(identity)
            if any(grading._matches(predicate, row) for predicate in predicates) and not critical:
                raise ValueError("Critical predicate lacks its actual original source join")
            if critical and (
                critical["saved_revision_sha256"] != grading.digest(reg["intent"])
                or any(
                    grading._clause(reg["intent"], name) is None
                    or grading.digest(grading._clause(reg["intent"], name)) != clause
                    for name, clause in critical["criterion_clause_sha256"].items()
                )
            ):
                raise ValueError(
                    "Critical original revision or clause differs from actual native source"
                )
            if row["condition"] not in control_sources:
                control_sources[row["condition"]] = controls.control_for_row(row, self.reading)
            control = control_sources[row["condition"]]
            if any(
                reg["source_bindings"].get(key) != value
                for key, value in {
                    "reading_source_sha256": control.source_digest,
                    "shim_sha256": control.module.CLOSURE_STUDY_SHIM_DIGEST,
                    "contract_sha256": control.module.CLOSURE_STUDY_CONTRACT_DIGEST,
                }.items()
            ):
                raise ValueError("An actual selected control source changed")
            measurement_key = grading.digest(
                {
                    "case": row["case"],
                    "arm": row["arm"],
                    "condition": row["condition"],
                    "model": reg.get("claude_model"),
                    "history": reg.get("include_history", False),
                }
            )
            if measurement_key not in measured:
                measured[measurement_key] = self._measure_source(reg, body, control)
            prompt, bindings, selected, names = measured[measurement_key]
            if (
                prompt != reg["prompt_digest"]
                or selected != reg["selected_ids"]
                or names != reg["expected_criteria"]
                or any(
                    bindings.get(k) != v
                    for k, v in reg["source_bindings"].items()
                    if k != "window_sha256"
                )
            ):
                raise ValueError(
                    "A registered row differs from its actual native dry source/control"
                )
            request = self.campaign.manifest["requests"]["replay"].get(reg["slot"])
            held = reg["slot"] in self.campaign.manifest.get("deferred_slots", {}).get("replay", [])
            if not held and request != reg["request_digest"]:
                raise ValueError("Registered request differs from canonical authority")
        if not required <= set(native_sources):
            raise ValueError("Every original native source must join the frozen inventory")

    def _measure_source(
        self, reg: dict[str, Any], body: dict[str, Any], control: Any
    ) -> tuple[Any, ...]:
        """Build actual native words transiently; cancellation cannot charge or store a reply."""
        config = replay._read_model_config(replay._runtime()[0], reg["claude_model"])
        selected_ids: list[str] = []
        names: list[str] = []
        original = control.module.build_prompt

        def captured(*args: Any, **kwargs: Any) -> Any:
            prompt, selected = original(*args, **kwargs)
            selected_ids[:] = [entry["id"] for entry in selected.entries]
            names[:] = list(
                control.module.constraints_for(selected.lines, claims=selected.asked_claims)
            )
            return prompt, selected

        control.module.build_prompt = captured
        key = reg["row"]["case"] + ":" + reg["row"]["arm"]
        measurements: dict[str, Any] = {}
        try:
            count = replay._read_cases(
                body,
                self.paths,
                level_cases._Spy(),
                replay.Ledger(replay.LEDGER_PATH),
                {},
                str(body.get("source") or "fixtures"),
                (reg["row"]["arm"],),
                dry_run=True,
                say=lambda _: None,
                selection=frozenset((key,)),
                include_history=reg.get("include_history", False),
                prompt_measurements=measurements,
                runtime_config=config,
                reading_override=control.module,
            )
        finally:
            control.module.build_prompt = original
            replay._remove_tree(os.path.join(self.paths["dir"], "scratch-read"))
        if count != 1 or set(measurements) != {key}:
            raise ValueError("A registered native source did not produce exactly one dry prompt")
        return measurements[key]["digest"], control.bindings(), selected_ids.copy(), names.copy()

    def _score(self, outputs: dict[str, Any], due: list[str], *, final: bool) -> dict[str, Any]:
        return grading.grade_frozen(
            self.frozen["protocol"],
            self.frozen["registrations"],
            self.frozen["blind"],
            self.frozen["protected"],
            self.expected,
            outputs,
            due_slots=due,
            final=final,
            reading_module=self.reading,
        )

    def _campaign_state(self) -> dict[str, Any]:
        state = self.campaign._state()
        if state.get("stop"):
            raise authority.LedgerError("The whole campaign is persistently stopped")
        return state

    def _coverage_stop(self) -> None:
        self.campaign.stop("coverage-failed")

    def _journal(self, state: dict[str, Any]) -> dict[str, Any]:
        calls = [c for c in state["calls"] if c["lane"] == "replay"]
        try:
            if not self.journal_path.exists():
                if calls or len(replay.Ledger(replay.LEDGER_PATH).calls()) != 631:
                    raise authority.LedgerError("Charged observations lost their journal")
                return {"v": 1, "authority": self.campaign.binding, "attempts": []}
            journal = _json(self.journal_path)
            attempts = journal["attempts"]
            if (
                journal.get("v") != 1
                or journal.get("authority") != self.campaign.binding
                or journal.get("pending")
                or len(attempts) != len(calls)
                or [a["shared_id"] for a in attempts] != [c["id"] for c in calls]
                or len({a["tag"] for a in attempts}) != len(attempts)
            ):
                raise authority.LedgerError(
                    "An interrupted, aliased or orphan native join blocks continuation"
                )
            native = replay.Ledger(replay.LEDGER_PATH).calls()
            if len(native) != 631 + len(attempts):
                raise authority.LedgerError("Native attempts do not join the shared charge stream")
            for n, (attempt, call) in enumerate(zip(attempts, calls, strict=True)):
                if (
                    attempt["slot"] != self.registrations[n]["slot"]
                    or attempt["row"] != self.registrations[n]["row"]
                    or attempt["shared_digest"] != authority.digest(call)
                    or attempt["native_index"] != 631 + n
                    or attempt["native_digest"] != authority.digest(native[631 + n])
                    or _json(self.folder / (attempt["shared_id"] + ".json")) != attempt
                ):
                    raise authority.LedgerError("Actual charged lineage was altered or reordered")
                self._output(attempt)
        except (
            ValueError,
            KeyError,
            TypeError,
            OSError,
            RuntimeError,
            authority.LedgerError,
        ) as error:
            self._coverage_stop()
            raise authority.LedgerError("Native operator evidence is missing or changed") from error
        return dict(journal)

    def _output(self, attempt: dict[str, Any]) -> dict[str, Any]:
        tag = attempt["tag"]
        if replay._tag_refusal(tag):
            raise authority.LedgerError("Actual tag is outside the native opaque scope")
        read_name, plan_name = replay._tagged(self.paths, tag)
        if (
            _sha(Path(read_name)) != attempt["read_sha256"]
            or _sha(Path(plan_name)) != attempt["plan_sha256"]
        ):
            raise authority.LedgerError("The newly written native artifact changed")
        stored = _json(Path(read_name))["cases"]
        row = attempt["row"]
        if set(stored) != {row["case"]} or set(stored[row["case"]]) != {row["arm"]}:
            raise authority.LedgerError("Native result is not exactly the registered cut and arm")
        native = replay.Ledger(replay.LEDGER_PATH).calls()[attempt["native_index"]]
        entry = stored[row["case"]][row["arm"]]
        if (
            native.get("key") != row["case"] + "|" + row["arm"]
            or native.get("read_scope") != replay._read_scope(read_name)
            or native.get("producer") != entry.get("producer")
            or entry.get("charged") is not True
        ):
            raise authority.LedgerError("The actual native charge does not own this tagged reply")
        page = replay._score_pages(_json(Path(self.paths["cases"])), self.paths, stored).get(
            (row["case"], row["arm"])
        )
        if not page or grading.digest(page) != attempt["page_digest"]:
            raise authority.LedgerError("Actual shipped Node page projection changed or is missing")
        return {"entry": entry, "page": page, "bindings": attempt["bindings"]}

    def grade(self, *, final: bool = False) -> dict[str, Any]:
        with authority.locked(str(self.journal_path)):
            self._validate_preparation()
            return self._grade(self._journal(self._campaign_state()), final=final)

    def _grade(self, journal: dict[str, Any], *, final: bool = False) -> dict[str, Any]:
        try:
            outputs = {a["slot"]: self._output(a) for a in journal["attempts"]}
            report = self._score(outputs, [a["slot"] for a in journal["attempts"]], final=final)
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
            if journal["attempts"]:
                self._coverage_stop()
            raise authority.LedgerError("Cumulative charged native grading is invalid") from error
        for field, reason in (
            ("protection_failures", "protection-failed"),
            ("semantic_failures", "semantic-failed"),
            ("coverage_failures", "coverage-failed"),
        ):
            if report[field]:
                self.campaign.stop(reason)
                break
        if journal["attempts"]:
            authority._write(str(self.folder / "report.json"), report)
        return report

    def run_next(self, *, claude_model: str, include_history: bool = False) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - one durable serial charge/join/grading transaction
        with authority.locked(str(self.journal_path)):
            self._validate_preparation()
            state = self._campaign_state()
            journal = self._journal(state)
            if journal["attempts"]:
                self._grade(journal)
                self._campaign_state()
            index = len(journal["attempts"])
            if index >= len(self.registrations):
                raise authority.LedgerError("The replay lane has no next registered row")
            reg = self.registrations[index]
            if reg["slot"] in self.campaign.manifest.get("deferred_slots", {}).get("replay", []):
                raise authority.LedgerError("The next slot remains explicitly held")
            if self.campaign.review_pending("replay", reg["slot"]):
                raise campaigns.AwaitingReviewError(
                    "The measured preceding batch awaits external review"
                )
            if claude_model != reg["claude_model"] or include_history != reg.get(
                "include_history", False
            ):
                raise ValueError("History selection differs from the frozen row")
            tag = uuid.uuid4().hex
            read_name, plan_name = replay._tagged(self.paths, tag)
            if (
                replay._tag_refusal(tag)
                or any(os.path.lexists(name) for name in (read_name, plan_name))
                or any(a["tag"] == tag for a in journal["attempts"])
            ):
                raise authority.LedgerError(
                    "A native repeat requires a fresh tag and absent artifacts"
                )
            control = controls.control_for_row(reg["row"], self.reading)
            selection = {
                "home": str(self.home),
                "tag": tag,
                "cases": (reg["row"]["case"] + ":" + reg["row"]["arm"],),
                "arms": (reg["row"]["arm"],),
                "include_history": include_history,
                "claude_model": claude_model,
                "reading_override": control.module,
                "say": lambda _: None,
            }
            before_shared = self.campaign._state()["calls"]
            before_native = replay.Ledger(replay.LEDGER_PATH).calls()
            if replay.read(**selection, dry_run=True) != 0:
                raise ValueError("The actual native dry plan refused this frozen row")
            plan = _json(Path(plan_name))
            bindings = control.bindings()
            key = selection["cases"][0]
            if (
                plan.get("calls") != 1
                or plan.get("selection") != [key]
                or set(plan.get("prompts") or {}) != {key}
                or plan["prompts"][key]["digest"] != reg["prompt_digest"]
                or any(
                    bindings.get(k) != v
                    for k, v in reg["source_bindings"].items()
                    if k != "window_sha256"
                )
                or bindings.get("prompt_sha256") != reg["prompt_digest"]
            ):
                raise ValueError(
                    "Actual native dry prompt/source/control differs from registration"
                )
            self._validate_preparation()
            self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            journal["pending"] = {"slot": reg["slot"], "tag": tag}
            authority._write(str(self.journal_path), journal)
            try:
                code = replay.read(**selection, dry_run=False)
                self._validate_preparation()
                shared = self.campaign._state()["calls"]
                native = replay.Ledger(replay.LEDGER_PATH).calls()
                if (
                    code != 0
                    or shared[: len(before_shared)] != before_shared
                    or native[: len(before_native)] != before_native
                    or len(shared) != len(before_shared) + 1
                    or len(native) != len(before_native) + 1
                ):
                    raise authority.LedgerError(
                        "One registered row did not produce one actual shared/native attempt"
                    )
                call = shared[-1]
                if (
                    call["lane"] != "replay"
                    or call["slot"] != reg["slot"]
                    or call["binding"] != reg["request_digest"]
                ):
                    raise authority.LedgerError("The newly charged shared request is unexpected")
                actual_bindings = control.bindings()
                if any(actual_bindings.get(k) != v for k, v in bindings.items()) or any(
                    actual_bindings.get(k) != v for k, v in reg["source_bindings"].items()
                ):
                    raise authority.LedgerError(
                        "The actual selected control changed between dry and real native calls"
                    )
                stored = _json(Path(read_name))["cases"]
                page = replay._score_pages(_json(Path(self.paths["cases"])), self.paths, stored)[
                    (reg["row"]["case"], reg["row"]["arm"])
                ]
                attempt = {
                    "slot": reg["slot"],
                    "row": reg["row"],
                    "tag": tag,
                    "shared_id": call["id"],
                    "shared_digest": authority.digest(call),
                    "native_index": len(before_native),
                    "native_digest": authority.digest(native[-1]),
                    "read_sha256": _sha(Path(read_name)),
                    "plan_sha256": _sha(Path(plan_name)),
                    "page_digest": grading.digest(page),
                    "bindings": actual_bindings,
                }
                self._output(attempt)
                with (self.folder / (call["id"] + ".json")).open("x", encoding="utf-8") as handle:
                    os.chmod(handle.name, 0o600)
                    json.dump(attempt, handle, sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                journal["attempts"].append(attempt)
                journal.pop("pending")
                authority._write(str(self.journal_path), journal)
                return self._grade(journal)
            except (Exception, KeyboardInterrupt):
                shared_now = self.campaign._state()["calls"]
                native_now = replay.Ledger(replay.LEDGER_PATH).calls()
                if shared_now == before_shared and native_now == before_native:
                    # A native refusal before reservation is a refused launch.
                    # Removing only its pending marker never refunds an attempt.
                    journal.pop("pending", None)
                    authority._write(str(self.journal_path), journal)
                else:
                    self._coverage_stop()
                raise

    def review_binding(self, report: dict[str, Any], *, batch: int | None) -> dict[str, Any]:
        state = self._campaign_state()
        slots = (
            self.campaign.manifest["slots"]["replay"]
            if batch is None
            else self.campaign.manifest["batches"]["replay"][batch]
        )
        calls = [
            call for call in state["calls"] if call["lane"] == "replay" and call["slot"] in slots
        ]
        return {
            "report_digest": report["report_digest"],
            "context": self._context(),
            "frozen_hashes": self.expected,
            "native_code_binding": native_code_binding(),
            "slots": slots,
            "attempts_digest": authority.digest(calls),
            "lineage_digest": authority.digest(self._journal(state)["attempts"]),
            "batch": batch,
        }

    def _accept(self, batch: int | None, review_path: Path) -> None:
        with authority.locked(str(self.journal_path)):
            self._validate_preparation()
            journal = self._journal(self._campaign_state())
            report = self._grade(journal, final=batch is None)
            if Path(review_path).resolve().is_relative_to(self.folder.resolve()):
                raise ValueError(
                    "Independent review must be produced outside the operator artifact directory"
                )
            review_source = _bytes(Path(review_path))
            review = json.loads(review_source)
            review_digest = hashlib.sha256(review_source).hexdigest()
            if (
                set(review) != {"v", "reviewer", "verdict", "binding"}
                or review["v"] != 1
                or review["verdict"] != "passed"
                or not isinstance(review["reviewer"], str)
                or not review["reviewer"].strip()
                or review["reviewer"] == "native-closure-operator"
                or review["binding"] != self.review_binding(report, batch=batch)
                or _sha(Path(review_path)) != review_digest
            ):
                raise ValueError("Independent review does not bind this report and actual attempts")
            slots = (
                self.campaign.manifest["slots"]["replay"]
                if batch is None
                else self.campaign.manifest["batches"]["replay"][batch]
            )
            proof = grading.acceptance_proof(
                report,
                self._context(),
                self.campaign._state()["calls"],
                slots,
                review_digest=review_digest,
                batch=batch,
            )
            if batch is None:
                self.campaign.accept("replay", proof)
            else:
                self.campaign.accept_batch("replay", batch, proof)

    def accept_batch(self, batch: int, review_path: Path) -> None:
        if type(batch) is not int or not 0 <= batch < len(
            self.campaign.manifest["batches"]["replay"]
        ):
            raise ValueError("The reviewed batch is outside the frozen authority")
        self._accept(batch, review_path)

    def accept_lane(self, review_path: Path) -> None:
        self._accept(None, review_path)
