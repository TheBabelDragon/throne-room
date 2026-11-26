# Throne Room Runtime Artifacts (v0.1)

Shared runtime service for ingesting, classifying, isolating, verifying, and
promoting execution artifacts across Throne Room subsystems.

A runtime artifact’s classification describes the evidence and handling policy
associated with that artifact. It does **not** establish the truth of its
contents or correctness of the originating implementation.

## Architecture

- **Content-addressed blobs** (SHA-256) under `runtime/artifacts/blobs/`
- **SQLite registry** (WAL) for runs, artifacts, verification records, promotion
  audit, promotion journal, and cross-process leases
- **Isolation tiers**: quarantine → sandbox → validated → certified → rejected
- **PromotionGate** is the only classification transition mechanism
- **Verifier adapters** with capability authorization (integrity vs formal)

Filesystem segregation is a storage boundary, **not** an OS-level execution
sandbox. Ingested artifacts are never executed automatically.

## SQLite WAL concurrency and durability

All registry, journal, and lock tables share one database file configured by
`throne_runtime.artifacts.sqlite_db.Database`:

| Setting | Value | Notes |
|---------|-------|-------|
| `journal_mode` | **WAL** | Verified on init and every connection; no silent DELETE fallback |
| `synchronous` | **FULL** (≥2) | Registry/journal durability; EXTRA accepted |
| `foreign_keys` | **ON** | Every connection |
| `busy_timeout` | **30000 ms** | Aligned with promotion lock timeouts |

### Guarantees

- Concurrent readers do not block writers (WAL).
- Writers serialize via short `BEGIN IMMEDIATE` transactions.
- Cross-process artifact promotion uses SQLite lease locks with ownership
  tokens, TTL, and **renewal** so long promotions do not silently expire.
- Audit insertion is idempotent by `promotion_id` primary key; conflicts are
  detected by exact field comparison.

### What WAL does *not* provide

- Atomicity across **SQLite and the artifact filesystem**. The promotion
  journal reconciles incomplete transitions after restart.
- Safe use on **network filesystems** (NFS, SMB, etc.). Require a **local
  single-host** filesystem for the database and blob store.
- Multi-host distributed locking or remote databases (out of scope for v0.1).

### Checkpoints

- Ordinary paths use SQLite’s automatic checkpointing.
- `Database.checkpoint_passive()` — non-blocking inspection/maintenance.
- `Database.checkpoint_full()` — controlled maintenance only; **not** during
  hot ingest/promote.
- Do not run `TRUNCATE` checkpoints on the hot path.

### Backup / restore

1. Prefer `sqlite3` backup API or stop writers and copy `registry.sqlite3`
   together with `-wal` and `-shm` if present.
2. After restore, open via `Database` (verifies WAL) and run
   `PRAGMA integrity_check`.
3. Run promotion recovery (`ArtifactService` startup) before accepting traffic.

### Diagnostics

```python
from throne_runtime.artifacts.sqlite_db import Database
db = Database("runtime/artifacts/registry.sqlite3")
print(db.wal_status())
print(db.integrity_check())
print(db.checkpoint_passive())
```

## Verifier capabilities

- `hash_bound_self_check` → `INTEGRITY_CHECK` only (VALIDATED tier)
- Formal certification requires `FORMAL_CERTIFICATE_VERIFICATION`
- Lean adapter remains **UNSUPPORTED** until a real Lean process is wired
- Keys: `THRONE_VERIFIER_KEYS_PATH` or explicit injection; no silent production
  ephemeral keys

## Promotion journal states

`PREPARED` → `DESTINATION_CREATED` → `DESTINATION_VERIFIED` →
`REGISTRY_UPDATED` → `AUDIT_COMMITTED` → `OLD_LOCATION_REMOVED` → `COMPLETED`

Also: `ROLLED_BACK`, `RECOVERY_REQUIRED` (retryable; not terminal).

## Operator recovery

```python
svc.promotion_gate.retry_recovery("promo-…")
svc.promotion_gate.journal.list_recovery_required()
```

Never discard the only verified blob copy automatically.
