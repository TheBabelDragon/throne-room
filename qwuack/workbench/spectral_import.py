"""Importer for spectral_experiment.v1 records from Signal Processor.

Signal Processor is the numerical authority.
Throne Room is the research / experimentation authority.

Offline JSON exchange only for this milestone.
Finite numerical evidence never becomes a formal proof.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind, utcnow
from qwuack.workbench.store import ObjectStore

CONTRACT_VERSION = "spectral_experiment.v1"
SUPPORTED_TYPES = {"quantum_wave_packet", "riemann_zeros", "spectral_comparison"}


class SpectralImportError(ValueError):
    """Malformed or incomplete spectral experiment."""


@dataclass
class ImportResult:
    ok: bool
    experiment_id: str = ""
    experiment_type: str = ""
    objects: list[MathObject] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "experiment_id": self.experiment_id,
            "experiment_type": self.experiment_type,
            "object_ids": [o.id for o in self.objects],
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _check_finite(obj: Any, path: str, errors: list[str]) -> None:
    if obj is None:
        return
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if not math.isfinite(obj):
            errors.append(f"non-finite number at {path}")
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_finite(v, f"{path}[{i}]", errors)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _check_finite(v, f"{path}.{k}", errors)


def validate_spectral_experiment(rec: dict[str, Any]) -> list[str]:
    """Structural + numerical validation. Returns list of errors (empty = ok)."""
    errors: list[str] = []
    if not isinstance(rec, dict):
        return ["not an object"]
    if rec.get("schema") != CONTRACT_VERSION:
        errors.append(f"schema must be {CONTRACT_VERSION}, got {rec.get('schema')!r}")
    if not rec.get("experiment_id"):
        errors.append("missing experiment_id")
    et = rec.get("experiment_type")
    if et not in SUPPORTED_TYPES:
        errors.append(f"experiment_type must be one of {sorted(SUPPORTED_TYPES)}")
    if not rec.get("engine_version"):
        errors.append("missing engine_version")
    if not rec.get("numerical_method"):
        errors.append("missing numerical_method")
    if not rec.get("timestamp"):
        errors.append("missing timestamp")
    if "parameters" not in rec or not isinstance(rec.get("parameters"), dict):
        errors.append("parameters must be an object")
    _check_finite(rec.get("measurements"), "measurements", errors)
    _check_finite(rec.get("output_summary"), "output_summary", errors)
    blob = json.dumps(rec.get("validation", {})) + json.dumps(rec.get("output_summary", {}))
    if any(tok in blob.lower() for tok in ("rh solved", "riemann hypothesis proved", "millennium solved")):
        errors.append("record attempts to declare RH/Millennium solved — rejected")
    return errors


def import_spectral_experiment(
    rec: dict[str, Any],
    store: ObjectStore,
    *,
    problem: str = "MATH-MP-02",
    worker: str = "spectral_import",
    session: str = "",
) -> ImportResult:
    """Validate and persist a spectral_experiment.v1 as typed MathObjects.

    Never sets formal verification to PASS from numerical evidence alone.
    """
    errors = validate_spectral_experiment(rec)
    if errors:
        return ImportResult(ok=False, errors=errors)

    eid = str(rec["experiment_id"])
    etype = str(rec["experiment_type"])
    warnings: list[str] = []
    created: list[MathObject] = []

    summary = rec.get("output_summary") or {}
    statement = (
        f"Imported {etype} experiment {eid} "
        f"(method={rec.get('numerical_method')})"
    )
    exp = store.mint(
        ObjectKind.EXPERIMENT,
        statement=statement,
        problem=problem,
        status=ClaimStatus.COMPUTATIONAL_EVIDENCE,
        evidence={
            "schema": CONTRACT_VERSION,
            "experiment_id": eid,
            "experiment_type": etype,
            "engine_version": rec.get("engine_version"),
            "numerical_method": rec.get("numerical_method"),
            "parameters": rec.get("parameters"),
            "units": rec.get("units"),
            "random_seed": rec.get("random_seed"),
            "output_summary": summary,
            "validation": rec.get("validation"),
            "limitations": rec.get("limitations") or [],
            "timestamp": rec.get("timestamp"),
            "dataset_keys": sorted((rec.get("datasets") or {}).keys()),
        },
        verification={
            "symbolic": "NOT_RUN",
            "numerical": "PASS",
            "literature": "NOT_RUN",
            "formal": "NOT_VERIFIED",
        },
        notes=[
            "Imported from Signal Processor spectral_experiment.v1",
            "Finite numerical evidence is never a formal proof of RH",
        ],
        worker=worker,
        session=session or eid,
    )
    created.append(exp)

    if etype == "quantum_wave_packet":
        meas = rec.get("measurements") or {}
        energy = (meas.get("energy") or {})
        result = store.mint(
            ObjectKind.RESULT,
            statement=(
                f"Quantum wave packet: \u27e8x\u27e9={meas.get('expectedPosition')}, "
                f"\u27e8p\u27e9={meas.get('expectedMomentum')}, E\u2248{energy.get('total')}, "
                f"norm_err={meas.get('normalizationError')}"
            ),
            problem=problem,
            status=ClaimStatus.COMPUTATIONAL_EVIDENCE,
            derived_from=[exp.id],
            evidence={"parent_experiment": eid, "measurements": meas},
            verification={"symbolic": "NOT_RUN", "numerical": "PASS", "literature": "NOT_RUN", "formal": "NOT_VERIFIED"},
            worker=worker,
            session=session or eid,
        )
        created.append(result)

    elif etype == "riemann_zeros":
        val = rec.get("validation") or {}
        meas = rec.get("measurements") or {}
        result = store.mint(
            ObjectKind.RESULT,
            statement=(
                f"Riemann zero candidates: count={meas.get('candidateCount')}, "
                f"matched_refs={val.get('matchedCandidates')}, "
                f"mean_spacing={meas.get('meanSpacing')}"
            ),
            problem=problem,
            status=ClaimStatus.COMPUTATIONAL_EVIDENCE,
            derived_from=[exp.id],
            evidence={
                "parent_experiment": eid,
                "validation": val,
                "measurements": meas,
                "note": val.get("note") or "Finite numerical verification is NOT a proof of RH",
            },
            verification={"symbolic": "NOT_RUN", "numerical": "PASS", "literature": "NOT_RUN", "formal": "NOT_VERIFIED"},
            notes=list(val.get("limitations") or []) + [
                "Never treat residual < \u03b5 as formal proof of a zero",
            ],
            worker=worker,
            session=session or eid,
        )
        created.append(result)

        hyp = store.mint(
            ObjectKind.HYPOTHESIS,
            statement=(
                "Normalized consecutive spacings of numerical zero candidates "
                "are consistent with a random-matrix ensemble (testable, not assumed)."
            ),
            problem=problem,
            status=ClaimStatus.CONJECTURE,
            derived_from=[exp.id, result.id],
            evidence={"parent_experiment": eid, "status": "open", "falsifiable": True},
            verification={"symbolic": "NOT_RUN", "numerical": "NOT_RUN", "literature": "NOT_RUN", "formal": "NOT_VERIFIED"},
            notes=["Falsifiable hypothesis only. No RH claim."],
            worker=worker,
            session=session or eid,
        )
        created.append(hyp)

    elif etype == "spectral_comparison":
        summary = rec.get("output_summary") or {}
        params = rec.get("parameters") or {}
        hyp_data = params.get("hypothesis") or {}
        hyp = store.mint(
            ObjectKind.HYPOTHESIS,
            statement=str(hyp_data.get("statement") or (
                "Spectral comparison between quantum observables and zero spacings "
                "(hypothesis only; no equivalence assumed)."
            )),
            problem=problem,
            status=ClaimStatus.CONJECTURE,
            derived_from=[exp.id],
            evidence={
                "parent_experiment": eid,
                "output_summary": summary,
                "falsifiable": True,
            },
            verification={"symbolic": "NOT_RUN", "numerical": "NOT_RUN", "literature": "NOT_RUN", "formal": "NOT_VERIFIED"},
            notes=[
                "No equivalence between quantum eigenvalues and Riemann zeros is assumed.",
                "Comparative numerical experiment only.",
            ],
            worker=worker,
            session=session or eid,
        )
        created.append(hyp)

        killer = store.mint(
            ObjectKind.COUNTEREXAMPLE,
            statement=(
                "Adversarial boundary: numerical spectral comparison cannot "
                "declare the Riemann Hypothesis solved."
            ),
            problem=problem,
            status=ClaimStatus.KILLED,
            derived_from=[exp.id, hyp.id],
            evidence={
                "parent_experiment": eid,
                "forbidden_shortcut": "finite numerical verification as RH proof",
            },
            verification={"symbolic": "NOT_RUN", "numerical": "NOT_RUN", "literature": "NOT_RUN", "formal": "NOT_VERIFIED"},
            notes=["Proof-killer boundary preserved."],
            worker=worker,
            session=session or eid,
        )
        created.append(killer)

    return ImportResult(
        ok=True,
        experiment_id=eid,
        experiment_type=etype,
        objects=created,
        warnings=warnings,
    )


def import_from_path(path: str | Path, store: ObjectStore, **kwargs) -> ImportResult:
    p = Path(path)
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ImportResult(ok=False, errors=[f"read/parse failed: {exc}"])
    return import_spectral_experiment(rec, store, **kwargs)


def import_from_json_string(text: str, store: ObjectStore, **kwargs) -> ImportResult:
    try:
        rec = json.loads(text)
    except json.JSONDecodeError as exc:
        return ImportResult(ok=False, errors=[f"parse failed: {exc}"])
    return import_spectral_experiment(rec, store, **kwargs)
