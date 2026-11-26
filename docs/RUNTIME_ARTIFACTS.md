# Runtime Artifact Distribution Service

Shared Throne Room infrastructure for receiving files and execution outputs,
assigning independent trust / evidence / isolation classifications, isolating
artifacts, recording provenance, and distributing them into appropriate storage.

> A runtime artifact’s classification describes the evidence and handling policy
> associated with that artifact. It does not establish the truth of its contents
> or correctness of the originating implementation.

## Architecture and data flow

```
ingest → scan (path/symlink/archive safety) → content-addressed blob store
      → registry record (QUARANTINED)
      → optional checks / verify
      → PromotionGate (only path to change tier/grade)
      → isolation tier directories + audit log
```

Package layout:

```
throne_runtime/artifacts/
  models.py       # independent classification enums + dataclasses
  manifest.py     # versioned, hashed, strictly validated manifests
  hashing.py      # SHA-256 content addressing
  scanner.py      # path traversal / symlink / archive safety
  isolation.py    # tier directories (quarantine/sandbox/validated/certified/rejected)
  registry.py     # SQLite runs / artifacts / promotions
  router.py       # policy-driven routing decisions
  promotion.py    # PromotionGate + append-only audit
  verifier.py     # integrity + formal-evidence presence checks
  storage.py      # LocalBlobStorage + StorageBackend protocol
  service.py      # ArtifactService public API
  cli.py          # throne-artifacts entrypoint
```

Runtime layout under `runtime/artifacts/`:

```
intake/ quarantine/ sandbox/ validated/ certified/ rejected/
blobs/  runs/  registry.sqlite3
```

## Manifest schema

```json
{
  "schema": "throne.runtime.artifact-manifest",
  "version": 1,
  "run_id": "run-…",
  "project": "Spacetime",
  "subsystem": "formal_verification",
  "run_type": "lean_build",
  "created_at": "UTC ISO-8601",
  "source_commit": "…",
  "parent_run": null,
  "trust": "UNTRUSTED",
  "evidence_grade": "EXPLORATORY",
  "isolation": "QUARANTINED",
  "sensitivity": "INTERNAL",
  "inputs": [],
  "outputs": [],
  "checks": [],
  "provenance": {},
  "status": "COMPLETED",
  "manifest_hash": "sha256…"
}
```

Malformed or unknown required fields are rejected. Manifests of failed runs are retained.

## Classification dimensions

| Axis | Values |
|------|--------|
| Trust | UNTRUSTED, TRUSTED |
| Evidence | EXPLORATORY, TESTED, NUMERICALLY_CROSSCHECKED, FORMALLY_PROVED, CERTIFIED |
| Isolation | QUARANTINED, SANDBOXED, VALIDATED, CERTIFIED_READ_ONLY, REJECTED |
| Sensitivity | PUBLIC, INTERNAL, RESTRICTED |

These axes are independent. Numerical cross-checking does not imply formal proof.
Self-declared high grades in a manifest do not grant promotion.

## Routing policy

See `policies/artifact_routing.yaml`. Default: new material → quarantine.
Experimental evidence → sandbox after checks. Formal certification requires
PromotionGate with verifier identity, version, target, PASS result, and
certificate hash. A certificate filename alone is insufficient.

## Isolation boundaries and limitations

v0.1 sandboxing is storage + process-boundary policy only. It is **not** a
claim of a complete OS security sandbox. No automatic execution of ingested
artifacts. Archives are inspected for path escapes before any extraction.

## Content-addressed storage

SHA-256 blobs under `blobs/ab/cd/<hash>`. Identical content deduplicates.
Registry metadata is separate. Writes use temporary staging + atomic replace.

## Promotion rules

`PromotionGate` is the only supported mechanism for changing classification or
tier. Every decision (ALLOWED or REJECTED) is appended to the audit log with
previous/new values, actor, policy rule, verifier evidence, and timestamps.
History is never erased on rejection or downgrade.

## Python API

```python
from pathlib import Path
from throne_runtime.artifacts import ArtifactService

svc = ArtifactService(root=Path("runtime/artifacts"))
run = svc.create_run(
    project="Spacetime",
    subsystem="formal_verification",
    run_type="lean_build",
    source_commit="abc123",
)
art = svc.ingest(run_id=run.run_id, path=Path("build.log"))
svc.add_check(run_id=run.run_id, name="lean_build", status="PASS")
result = svc.verify(run_id=run.run_id)
svc.list_runs(project="Spacetime")
svc.export_run(run.run_id, destination=Path("export"))
```

## CLI examples

```bash
throne-artifacts init
throne-artifacts create-run --project Spacetime --type lean_build
throne-artifacts ingest --run RUN_ID path/to/file
throne-artifacts show RUN_ID
throne-artifacts list --project Spacetime
throne-artifacts verify RUN_ID
throne-artifacts promote ARTIFACT_ID --target validated
throne-artifacts export RUN_ID --output ./export
throne-artifacts audit RUN_ID
```

## Existing subsystem integration

Additive only. Does not replace Duck Workbench `ObjectStore`, Millennium Lab
evidence semantics, observer journals, Field Intelligence live paths, or Qwuack
ownership. Optional export helpers may be added later for snapshots/reports
without moving operational journals. Yang–Mills Lean certificate artifact type
is future-compatible; this release does not claim formal certificates exist.

## Recovery and integrity

- Re-hash blobs on verify; mismatch fails the run.
- Registry survives process restart (SQLite).
- Export bundles include manifest, artifacts, and promotion audit.

## Future distributed storage

`StorageBackend` protocol allows remote/object-store backends without rewriting
`ArtifactService`.
