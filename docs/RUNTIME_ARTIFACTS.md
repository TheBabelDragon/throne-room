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
      → VerifierAdapter execution (when required)
      → PromotionGate (only path to change tier/grade; real storage move)
      → isolation tier directories + append-only audit log
```

Package layout:

```
throne_runtime/artifacts/
  models.py       # independent classification enums + dataclasses
  manifest.py     # versioned, hashed, strictly validated manifests
  hashing.py      # SHA-256 content addressing
  scanner.py      # path traversal / symlink / archive safety
  isolation.py    # tier directories (quarantine/sandbox/validated/certified/rejected)
  registry.py     # SQLite UPSERT runs / artifacts / promotions / verification records
  router.py       # YAML policy-driven routing decisions
  policy.py       # load/validate artifact_routing.yaml
  promotion.py    # PromotionGate + permitted transitions + storage move
  verifier.py     # integrity verification (missing blobs fail)
  verifiers.py    # VerifierAdapter contract + execution records
  storage.py      # LocalBlobStorage + StorageBackend protocol
  service.py      # ArtifactService public API
  cli.py          # throne-artifacts entrypoint
```

## Verifier guarantees (critical)

- A caller **cannot** establish certification by passing `verification_result=PASS`.
- Certification requires a **VerifierAdapter** that actually executes (or invokes)
  an independently trusted process and returns a sealed `VerificationExecutionRecord`.
- Records bind: artifact SHA-256, source commit, proof target, verifier id/version.
- `record_hash` seals the binding; mismatched or replayed records are rejected.
- Unsupported verifier types (including Lean in v0.1) return `UNSUPPORTED` and
  cannot satisfy CERTIFIED / FORMALLY_PROVED gates.
- Certificate filename or hash alone is never sufficient.

## Classification authority

Incoming `trust=TRUSTED` or `evidence_grade=FORMALLY_PROVED|CERTIFIED` on
`create_run` are treated as claims and forced back to UNTRUSTED / EXPLORATORY.
Only PromotionGate may elevate classification, and only with the appropriate
execution evidence.

## Promotion storage transition

PromotionGate:

1. Validates permitted isolation transitions.
2. Requires integrity execution evidence for VALIDATED.
3. Requires independent verifier PASS execution record for CERTIFIED_READ_ONLY.
4. Places content into the destination tier and verifies destination hash.
5. Updates registry metadata.
6. Removes old-tier layout exposure after successful update.
7. On failure, rolls metadata back and appends a ROLLBACK audit entry.

Audit history is append-only and never erased.

## Routing policy

YAML files under `policies/` are loaded at service init. New intake is always
quarantined. Failed checks route toward rejected. Formal claims are never
auto-promoted.

## Isolation boundaries and limitations

v0.1 sandboxing is storage + process-boundary policy only. It is **not** a
claim of a complete OS security sandbox. No automatic execution of ingested
artifacts. Archives are inspected for path escapes before any extraction.

## Content-addressed storage

SHA-256 blobs under `blobs/ab/cd/<hash>`. Identical content deduplicates.
Registry metadata is separate. Writes use temporary staging + atomic replace.
Run updates use SQLite `ON CONFLICT DO UPDATE` (UPSERT) so foreign keys to
artifacts are preserved.

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
# Promotion requires real verifier execution for high tiers
svc.promote(art.artifact_id, target="VALIDATED", actor="operator")
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
ownership. Yang–Mills Lean certificate artifact type is future-compatible;
this release does not claim formal certificates exist and does not invoke Lean.

## Recovery and integrity

- Re-hash blobs on verify; missing or mismatched blobs fail the run.
- Manifest hash verified on registry retrieval.
- Registry survives process restart (SQLite).
- Export bundles include manifest, artifacts, and promotion audit.

## Future distributed storage

`StorageBackend` protocol allows remote/object-store backends without rewriting
`ArtifactService`. Additional VerifierAdapter implementations (real Lean, pytest
harness, etc.) register into `VerifierRegistry`.
