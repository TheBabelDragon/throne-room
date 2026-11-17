"""QUANTUM / RIEMANN POND — experimental research desk for spectral experiments.

Extends the Duck Workbench without replacing the existing Riemann pond
in qwuack.millennium.ponds.

The Duck can:
  - inspect imported wave packets / zero datasets
  - compare spectral distributions
  - generate testable hypotheses
  - preserve failed experiments and counterexamples
  - track confidence and numerical limitations

The Duck cannot:
  - mutate live FieldTick
  - obtain act.device
  - declare RH solved from finite numerical evidence
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind, utcnow
from qwuack.workbench.spectral_import import (
    CONTRACT_VERSION,
    ImportResult,
    import_from_json_string,
    import_from_path,
    import_spectral_experiment,
    validate_spectral_experiment,
)
from qwuack.workbench.store import ObjectStore

POND_NAME = "QUANTUM / RIEMANN POND"
PROBLEM = "MATH-MP-02"  # Riemann research environment
JOURNAL = Path("/tmp/metafield/spectral_pond.jsonl")


@dataclass
class PondSnapshot:
    active_experiment_id: str | None = None
    quantum_observations: list[str] = field(default_factory=list)
    riemann_observations: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    counterexamples: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)
    next_recommended: str = ""
    ts: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "pond": POND_NAME,
            "problem": PROBLEM,
            "active_experiment_id": self.active_experiment_id,
            "quantum_observations": self.quantum_observations,
            "riemann_observations": self.riemann_observations,
            "hypotheses": self.hypotheses,
            "counterexamples": self.counterexamples,
            "provenance": self.provenance,
            "validation_notes": self.validation_notes,
            "next_recommended": self.next_recommended,
            "ts": self.ts or utcnow(),
        }


class SpectralPond:
    """Research desk that consumes spectral_experiment.v1 records."""

    def __init__(self, store: ObjectStore | None = None, root: Path | None = None) -> None:
        self.store = store or ObjectStore(root=root)
        self.history: list[ImportResult] = []
        self.active: MathObject | None = None

    def ingest(self, rec: dict[str, Any], *, session: str = "") -> ImportResult:
        result = import_spectral_experiment(
            rec, self.store, problem=PROBLEM, worker="spectral_pond", session=session
        )
        self.history.append(result)
        if result.ok and result.objects:
            self.active = result.objects[0]
            self._append_journal({"event": "ingest", "result": result.as_dict()})
        return result

    def ingest_path(self, path: str | Path, **kwargs) -> ImportResult:
        result = import_from_path(path, self.store, problem=PROBLEM, worker="spectral_pond", **kwargs)
        self.history.append(result)
        if result.ok and result.objects:
            self.active = result.objects[0]
            self._append_journal({"event": "ingest_path", "path": str(path), "result": result.as_dict()})
        return result

    def ingest_json(self, text: str, **kwargs) -> ImportResult:
        result = import_from_json_string(text, self.store, problem=PROBLEM, worker="spectral_pond", **kwargs)
        self.history.append(result)
        if result.ok and result.objects:
            self.active = result.objects[0]
            self._append_journal({"event": "ingest_json", "result": result.as_dict()})
        return result

    def snapshot(self) -> PondSnapshot:
        objs = list(self.store.of_problem(PROBLEM))
        quantum = [
            o.statement for o in objs
            if o.kind == ObjectKind.RESULT and "Quantum wave" in o.statement
        ]
        riemann = [
            o.statement for o in objs
            if o.kind == ObjectKind.RESULT and "Riemann zero" in o.statement
        ]
        hyps = [
            o.statement for o in objs
            if o.kind == ObjectKind.HYPOTHESIS and o.status in {
                ClaimStatus.CONJECTURE, ClaimStatus.OPEN, ClaimStatus.EXPLORING
            }
        ]
        counters = [
            o.statement for o in objs
            if o.kind == ObjectKind.COUNTEREXAMPLE
        ]
        provenance = []
        for o in objs:
            if o.kind == ObjectKind.EXPERIMENT:
                provenance.append({
                    "id": o.id,
                    "type": (o.evidence or {}).get("experiment_type"),
                    "experiment_id": (o.evidence or {}).get("experiment_id"),
                    "status": o.status.value,
                    "formal": (o.verification or {}).get("formal"),
                })

        notes = [
            "Finite numerical verification is NOT a proof of RH",
            "No experiment can set verification.formal = PASS for RH",
            "Existing Riemann pond in millennium remains intact",
        ]
        next_rec = (
            "Import a bounded riemann_zeros experiment and a quantum_wave_packet, "
            "then run a spectral_comparison; inspect hypotheses and counterexamples."
        )
        if not provenance:
            next_rec = "Import a spectral_experiment.v1 JSON record from Signal Processor."

        snap = PondSnapshot(
            active_experiment_id=self.active.id if self.active else None,
            quantum_observations=quantum[-5:],
            riemann_observations=riemann[-5:],
            hypotheses=hyps[-5:],
            counterexamples=counters[-5:],
            provenance=provenance[-10:],
            validation_notes=notes,
            next_recommended=next_rec,
            ts=utcnow(),
        )
        self._append_journal({"event": "snapshot", "snapshot": snap.as_dict()})
        return snap

    def generate_hypothesis(self, statement: str, *, derived_from: list[str] | None = None) -> MathObject:
        """Duck generates a testable hypothesis. Always open / conjecture status."""
        obj = self.store.mint(
            ObjectKind.HYPOTHESIS,
            statement=statement,
            problem=PROBLEM,
            status=ClaimStatus.CONJECTURE,
            derived_from=derived_from or [],
            evidence={"falsifiable": True, "source": "spectral_pond"},
            verification={
                "symbolic": "NOT_RUN",
                "numerical": "NOT_RUN",
                "literature": "NOT_RUN",
                "formal": "NOT_VERIFIED",
            },
            notes=["Generated by QUANTUM / RIEMANN POND. Not a proof."],
            worker="spectral_pond",
        )
        self._append_journal({"event": "hypothesis", "id": obj.id, "statement": statement})
        return obj

    def adversarial_check(self) -> MathObject:
        """Demonstrate that no experiment can declare RH solved."""
        obj = self.store.mint(
            ObjectKind.COUNTEREXAMPLE,
            statement=(
                "Adversarial validation: any claim that finite zero verification "
                "solves the Riemann Hypothesis is rejected and stored as KILLED."
            ),
            problem=PROBLEM,
            status=ClaimStatus.KILLED,
            evidence={
                "forbidden_shortcut": "finite numerical verification as RH proof",
                "registry_rule": "MATH-MP-02",
            },
            verification={
                "symbolic": "NOT_RUN",
                "numerical": "NOT_RUN",
                "literature": "NOT_RUN",
                "formal": "NOT_VERIFIED",
            },
            notes=["Proof-killer boundary. Official RH status remains open."],
            worker="spectral_pond",
        )
        self._append_journal({"event": "adversarial_check", "id": obj.id})
        return obj

    def render_desk(self) -> str:
        snap = self.snapshot()
        lines = [
            f"=== {POND_NAME} ===",
            f"problem: {PROBLEM} (official status: open)",
            f"active: {snap.active_experiment_id or chr(0x2014)}",
            "",
            "quantum observations:",
        ]
        for q in snap.quantum_observations or ["(none)"]:
            lines.append(f"  \u00b7 {q}")
        lines.append("riemann observations:")
        for r in snap.riemann_observations or ["(none)"]:
            lines.append(f"  \u00b7 {r}")
        lines.append("hypotheses:")
        for h in snap.hypotheses or ["(none)"]:
            lines.append(f"  \u00b7 {h}")
        lines.append("counterexamples / killed:")
        for c in snap.counterexamples or ["(none)"]:
            lines.append(f"  \u00b7 {c}")
        lines.append("provenance (recent experiments):")
        for p in snap.provenance or []:
            lines.append(
                f"  \u00b7 {p.get('id')} type={p.get('type')} "
                f"status={p.get('status')} formal={p.get('formal')}"
            )
        lines.append("")
        lines.append("validation:")
        for n in snap.validation_notes:
            lines.append(f"  ! {n}")
        lines.append(f"next: {snap.next_recommended}")
        text = "\n".join(lines) + "\n"
        desk_path = Path("/tmp/metafield/spectral_desk.txt")
        desk_path.parent.mkdir(parents=True, exist_ok=True)
        desk_path.write_text(text, encoding="utf-8")
        return text

    def _append_journal(self, row: dict[str, Any]) -> None:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        row = dict(row)
        row.setdefault("ts", utcnow())
        with JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


def demo_roundtrip() -> dict[str, Any]:
    """Acceptance helper: synthetic quantum + riemann import, hypothesis, adversarial."""
    store = ObjectStore(root=Path("/tmp/metafield_spectral_demo"))
    for p in store.root.glob("*"):
        if p.is_file():
            p.unlink()
    store = ObjectStore(root=Path("/tmp/metafield_spectral_demo"))
    pond = SpectralPond(store=store)

    quantum_rec = {
        "schema": CONTRACT_VERSION,
        "experiment_id": "exp_quantum_demo_001",
        "experiment_type": "quantum_wave_packet",
        "engine_version": "spectral-experiment.v1",
        "parameters": {"potential": "free", "steps": 20},
        "units": "dimensionless",
        "random_seed": 0,
        "numerical_method": "split-step-fourier",
        "output_summary": {"energy": 0.5, "normalizationError": 1e-9},
        "measurements": {
            "expectedPosition": 0.1,
            "expectedMomentum": 1.0,
            "energy": {"total": 0.5, "kinetic": 0.5, "potential": 0.0},
            "normalizationError": 1e-9,
        },
        "validation": {"note": "demo"},
        "limitations": ["Finite grid"],
        "timestamp": utcnow(),
    }
    riemann_rec = {
        "schema": CONTRACT_VERSION,
        "experiment_id": "exp_riemann_demo_001",
        "experiment_type": "riemann_zeros",
        "engine_version": "spectral-experiment.v1",
        "parameters": {"tMin": 14, "tMax": 30},
        "units": "ordinate-t",
        "random_seed": 0,
        "numerical_method": "riemann-siegel-approx + sign-change-bisection",
        "output_summary": {"candidateCount": 3, "matchedReferences": 2},
        "measurements": {"candidateCount": 3, "meanSpacing": 5.0},
        "validation": {
            "note": "Finite numerical verification is NOT a proof of the Riemann Hypothesis.",
            "matchedCandidates": 2,
            "limitations": ["Approximate remainder"],
        },
        "limitations": ["Approximate remainder"],
        "timestamp": utcnow(),
    }

    q = pond.ingest(quantum_rec, session="demo")
    r = pond.ingest(riemann_rec, session="demo")
    hyp = pond.generate_hypothesis(
        "Normalized spacing of numerical zero candidates is statistically "
        "indistinguishable from GUE for this height window (testable).",
        derived_from=[o.id for o in (q.objects + r.objects) if o],
    )
    adv = pond.adversarial_check()
    desk = pond.render_desk()

    any_proof = any(o.is_proof for o in pond.store)
    return {
        "quantum_ok": q.ok,
        "riemann_ok": r.ok,
        "hypothesis_id": hyp.id,
        "adversarial_id": adv.id,
        "any_formal_proof": any_proof,
        "object_count": len(pond.store),
        "minted_ids": [o.id for o in (q.objects + r.objects + [hyp, adv])],
        "desk_preview": desk[:500],
    }
