"""Zero-finder diagnostics, precision escalation, validation result format."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from qwuack.spectral_ref.reference import (
    FIXTURE_SET_VERSION,
    REFERENCE_ENGINE_VERSION,
    hardy_z_reference,
)

RESULT_SCHEMA = "spectral_validation_result.v0.3"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ValidationRecord:
    schema: str = RESULT_SCHEMA
    classification: str = "INCONCLUSIVE"
    test_id: str = ""
    fixture_id: str = ""
    engine: str = ""
    engine_version: str = ""
    reference_engine: str = REFERENCE_ENGINE_VERSION
    fixture_set_version: str = FIXTURE_SET_VERSION
    precision: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    production: dict[str, Any] = field(default_factory=dict)
    reference: dict[str, Any] = field(default_factory=dict)
    residuals: dict[str, Any] = field(default_factory=dict)
    convergence: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    timestamp: str = ""
    commit_sha: str = ""
    repo: str = "throne-room"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["timestamp"]:
            d["timestamp"] = utcnow()
        return d


def classify_hardy_z(
    abs_residual: float,
    *,
    at_known_zero: bool,
    production_finite: bool,
    ref_finite: bool,
    abs_tol: float | None = None,
    rel_tol: float | None = None,
    rel_residual: float | None = None,
) -> str:
    if not production_finite:
        return "NUMERICAL_INSTABILITY"
    if not ref_finite:
        return "REFERENCE_UNAVAILABLE"
    if at_known_zero:
        tol = abs_tol if abs_tol is not None else 1e-3
        return "PASS" if abs_residual <= tol else "FAIL"
    if rel_tol is not None and rel_residual is not None:
        return "PASS" if rel_residual <= rel_tol else "FAIL"
    if abs_tol is not None:
        return "PASS" if abs_residual <= abs_tol else "FAIL"
    return "INCONCLUSIVE"


def compare_hardy_z_production(
    t: float,
    production_Z: float,
    *,
    dps: int = 25,
    fixture_id: str = "",
    test_id: str = "hardy_z_compare",
    engine_version: str = "riemann-spectral.v1",
    at_known_zero: bool = False,
    abs_tol: float | None = None,
    rel_tol: float | None = 0.05,
) -> ValidationRecord:
    ref = hardy_z_reference(t, dps=dps)
    prod_finite = math.isfinite(production_Z)
    abs_res = abs(production_Z - ref["Z"]) if prod_finite and ref["finite"] else float("nan")
    denom = max(abs(ref["Z"]), 1e-30)
    rel_res = abs_res / denom if math.isfinite(abs_res) else float("nan")
    if at_known_zero:
        abs_res_vs_zero = abs(production_Z) if prod_finite else float("nan")
        classification = classify_hardy_z(
            abs_res_vs_zero,
            at_known_zero=True,
            production_finite=prod_finite,
            ref_finite=ref["finite"],
            abs_tol=abs_tol if abs_tol is not None else 1e-3,
        )
        residuals = {
            "abs_vs_reference": abs_res,
            "abs_vs_zero": abs_res_vs_zero,
            "rel_vs_reference": rel_res,
            "reference_abs_Z": ref["abs_Z"],
        }
    else:
        classification = classify_hardy_z(
            abs_res,
            at_known_zero=False,
            production_finite=prod_finite,
            ref_finite=ref["finite"],
            rel_tol=rel_tol,
            rel_residual=rel_res if math.isfinite(rel_res) else None,
            abs_tol=abs_tol,
        )
        residuals = {
            "abs_vs_reference": abs_res,
            "rel_vs_reference": rel_res,
            "reference_abs_Z": ref["abs_Z"],
        }
    return ValidationRecord(
        classification=classification,
        test_id=test_id,
        fixture_id=fixture_id,
        engine="production_js_or_adapter",
        engine_version=engine_version,
        precision={"dps": dps, "production": "float64"},
        inputs={"t": t},
        production={"Z": production_Z, "finite": prod_finite},
        reference=ref,
        residuals=residuals,
        notes=[
            "Finite numerical verification is NOT a proof of RH",
            "PASS/FAIL is numerical acceptance only",
        ],
    )


def zero_finder_diagnostic(
    expected_t: float,
    detected_t: float,
    production_Z_at_detected: float,
    *,
    iterations: int | None = None,
    convergence: str = "unknown",
    fixture_id: str = "",
    dps: int = 25,
    abs_offset_tol: float = 0.05,
) -> ValidationRecord:
    ref = hardy_z_reference(expected_t, dps=dps)
    offset = abs(detected_t - expected_t)
    prod_finite = math.isfinite(production_Z_at_detected)
    if not prod_finite:
        cls = "NUMERICAL_INSTABILITY"
    elif offset <= abs_offset_tol and abs(production_Z_at_detected) < 0.1:
        cls = "PASS"
    elif offset <= abs_offset_tol:
        cls = "INCONCLUSIVE"
    else:
        cls = "FAIL"
    return ValidationRecord(
        classification=cls,
        test_id="zero_finder_diagnostic",
        fixture_id=fixture_id,
        engine="production_zero_finder",
        engine_version="riemann-spectral.v1",
        precision={"dps": dps, "production": "float64"},
        inputs={"expected_t": expected_t},
        production={
            "detected_t": detected_t,
            "Z_at_detected": production_Z_at_detected,
            "finite": prod_finite,
        },
        reference=ref,
        residuals={
            "abs_ordinate_offset": offset,
            "Z_residual_at_detected": abs(production_Z_at_detected) if prod_finite else None,
        },
        convergence={"status": convergence, "iterations": iterations},
        notes=[
            "Zero-finder must locate roots independently; known zeros not injected into output",
        ],
    )


def precision_escalation_study(
    t: float,
    production_evaluator: Callable[[float], float],
    dps_list: list[int] | None = None,
) -> list[ValidationRecord]:
    dps_list = dps_list or [15, 25, 40]
    rows: list[ValidationRecord] = []
    try:
        prod_Z = float(production_evaluator(t))
    except Exception as exc:  # noqa: BLE001
        return [ValidationRecord(
            classification="NUMERICAL_INSTABILITY",
            test_id="precision_escalation",
            inputs={"t": t},
            notes=[f"production evaluator raised: {exc}"],
        )]
    for dps in dps_list:
        rows.append(compare_hardy_z_production(
            t, prod_Z, dps=dps, test_id=f"precision_escalation_dps{dps}",
            at_known_zero=False, rel_tol=0.05,
        ))
    return rows


def append_result(path: Path, record: ValidationRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.as_dict()) + "\n"
    prev = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(prev + line, encoding="utf-8")
