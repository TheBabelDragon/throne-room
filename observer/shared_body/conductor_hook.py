"""Optional conductor-side hook for SHARED_BODY.

Safe to call from observer.startup digest loop.
Never opens UDP. Never raises into the control loop.
"""

from __future__ import annotations

from typing import Any

_registry = None


def get_registry():
    global _registry
    if _registry is None:
        try:
            from .registry import SharedBodyRegistry

            _registry = SharedBodyRegistry(auto_persist=True)
        except Exception:
            _registry = None
    return _registry


def on_digest_tick(
    packets: list[dict[str, Any]],
    field_snap: dict[str, Any] | None = None,
    head_snap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest recent FO packets into the SHARED_BODY registry.

    Returns a small status dict for the digest (never raises).
    """
    status: dict[str, Any] = {
        "shared_body": "off",
        "ingested": 0,
        "rejected": 0,
        "n_bodies": 0,
    }
    try:
        from .adapter import ingest_packet
        from .export import snapshot_to_reverie

        reg = get_registry()
        if reg is None:
            return status

        ingested = 0
        rejected = 0
        for pkt in packets:
            if not isinstance(pkt, dict):
                continue
            body, reason = ingest_packet(
                pkt,
                reg,
                field_snap=field_snap,
                head_snap=head_snap,
            )
            if body is not None and reason == "ok":
                ingested += 1
            else:
                rejected += 1

        try:
            snapshot_to_reverie(registry=reg)
        except Exception:
            pass

        counts = reg.counts()
        status.update(
            {
                "shared_body": "live",
                "ingested": ingested,
                "rejected": rejected,
                "n_bodies": counts.get("total", 0),
                "alive": counts.get("alive", 0),
                "stale": counts.get("stale", 0),
                "timeout": counts.get("timeout", 0),
            }
        )
    except Exception as e:
        status["shared_body"] = "error"
        status["error"] = str(e)[:200]
    return status
