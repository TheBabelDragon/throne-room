"""Adapters: live Throne Room packets ↔ agent contracts.

Existing surfaces stay authoritative:

- observer ingest emits FieldObservation / wifi_csi
- aurora.policies.Intent is fail-closed swarm policy
- this module only *translates*

Aurora never gains act.device through this path. Wrapping an Intent as
an ActionProposal lets SELF see it; Redis ESCAPE still gates fire.
"""

from __future__ import annotations

from typing import Any

from agent.hashutil import uid
from agent.operator_abi import make_proposal
from agent.schemas import (
    AURORA_TO_ACTION,
    ActionProposal,
    FieldObservation,
    FieldRegion,
    PerceptionEvent,
)


def packet_to_observation(packet: dict[str, Any]) -> FieldObservation | None:
    """Accept either canonical MetaField FO or a wifi_csi dict."""
    if not isinstance(packet, dict):
        return None

    if packet.get("type") == "wifi_csi" or ("csi" in packet and "node" in packet):
        body = str(packet.get("node") or packet.get("body_id") or "csi-unknown")
        csi_raw = packet.get("csi") or []
        try:
            csi = [float(x) for x in csi_raw]
        except (TypeError, ValueError):
            csi = []
        rssi = float(packet.get("rssi", -80))
        mean = sum(csi) / len(csi) if csi else 0.0
        peak = max(csi) if csi else 0.0
        energy = (sum(v * v for v in csi) / len(csi)) ** 0.5 if csi else 0.0
        if csi and len(csi) > 1:
            var = sum((v - mean) ** 2 for v in csi) / len(csi)
            spread = var ** 0.5
        else:
            spread = 0.0
        rssi_n = max(0.0, min(1.0, (rssi + 90.0) / 60.0))
        return FieldObservation(
            body_id=body,
            body_type="wifi_csi",
            timestamp=str(packet.get("timestamp") or ""),
            regions=[
                FieldRegion("rssi", rssi_n, 1.0),
                FieldRegion("csi_mean", max(0.0, min(1.0, mean)), 0.95),
                FieldRegion("csi_peak", max(0.0, min(1.0, peak)), 0.95),
                FieldRegion("csi_energy", max(0.0, min(1.0, energy)), 0.9),
                FieldRegion("csi_spread", max(0.0, min(1.0, spread * 2.0)), 0.85),
            ],
            csi=csi,
            rssi_dbm=rssi,
            synthetic=False,
            valid=True,
        )

    if "field_regions" in packet and "body_id" in packet:
        regions: list[FieldRegion] = []
        for r in packet.get("field_regions") or []:
            if not isinstance(r, dict):
                continue
            try:
                regions.append(
                    FieldRegion(
                        name=str(r.get("region") or "unknown"),
                        observed=float(r.get("observed") or 0.0),
                        confidence=float(r.get("confidence") or 1.0),
                    )
                )
            except (TypeError, ValueError):
                continue
        modality = packet.get("modality") or {}
        wifi = modality.get("wifi_csi") if isinstance(modality, dict) else {}
        csi = []
        rssi = -90.0
        if isinstance(wifi, dict):
            try:
                csi = [float(x) for x in (wifi.get("csi") or [])]
            except (TypeError, ValueError):
                csi = []
            try:
                rssi = float(wifi.get("rssi_dbm") if wifi.get("rssi_dbm") is not None else -90)
            except (TypeError, ValueError):
                rssi = -90.0
        return FieldObservation(
            body_id=str(packet.get("body_id")),
            body_type=str(packet.get("body_type") or "wifi_csi"),
            timestamp=str(packet.get("timestamp") or ""),
            regions=regions,
            csi=csi,
            rssi_dbm=rssi,
            synthetic=False,
            valid=str(packet.get("health") or "ok") != "error",
        )
    return None


def packet_to_perception(packet: dict[str, Any], tick: int) -> PerceptionEvent | None:
    from agent.perception import observation_to_perception

    obs = packet_to_observation(packet)
    if obs is None:
        return None
    return observation_to_perception(obs, tick)


def aurora_intent_to_proposal(
    intent: Any,
    *,
    observation_id: str = "",
    agent_id: str = "aurora-0",
) -> ActionProposal:
    """Wrap aurora.policies.Intent (or a dict from aurora_actions.jsonl)."""
    if hasattr(intent, "action"):
        action = str(intent.action)
        priority = float(getattr(intent, "priority", 0.0))
        reason = str(getattr(intent, "reason", ""))
        body_id = getattr(intent, "body_id", None)
        params = dict(getattr(intent, "params", None) or {})
    else:
        action = str(intent.get("action") or intent.get("type") or "hold")
        priority = float(intent.get("priority") or 0.0)
        reason = str(intent.get("reason") or "")
        body_id = intent.get("body_id")
        params = dict(intent.get("params") or {})

    action_type = AURORA_TO_ACTION.get(action, "WAIT")
    if body_id:
        params.setdefault("body_id", str(body_id))
    params.setdefault("priority", round(priority, 3))
    if action_type == "PROBE":
        params.setdefault("magnitude", min(0.9, 0.35 + priority * 0.4))
    if action_type == "ATTEND":
        params.setdefault("target", str(body_id or "csi"))
    if action_type == "WAIT":
        params.setdefault("text", reason)

    return make_proposal(
        action_type=action_type,
        parameters=params,
        target=str(body_id or params.get("target") or "field"),
        rationale=f"aurora:{action} {reason}".strip(),
        confidence=min(1.0, max(0.1, priority)),
        originating_observation=observation_id or uid("obs"),
        agent_id=agent_id,
    )


def proposal_to_aurora_action(proposal: ActionProposal) -> dict[str, Any]:
    """Project an ABI proposal onto Aurora's existing journal shape.

    This is a view, not a fire. Dispatch still requires RedisControl.allowed.
    """
    inverse = {v: k for k, v in AURORA_TO_ACTION.items()}
    aurora_type = inverse.get(proposal.action_type, "hold")
    if proposal.action_type == "SPEAK":
        aurora_type = "attention"
    return {
        "type": aurora_type,
        "action": aurora_type,
        "priority": round(float(proposal.confidence), 3),
        "reason": proposal.rationale,
        "body_id": proposal.parameters.get("body_id"),
        "params": proposal.parameters,
        "source": "agent.operator_abi",
        "schema_version": 1,
        "proposal_id": proposal.proposal_id,
        "action_type": proposal.action_type,
        "capability": proposal.capability,
    }
