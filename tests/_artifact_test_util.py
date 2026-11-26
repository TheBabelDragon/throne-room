"""Shared helpers for runtime artifact tests."""

from pathlib import Path

from throne_runtime.artifacts.service import ArtifactService

POLICY = Path(__file__).resolve().parents[1] / "policies"


def make_service(root: Path, **kwargs) -> ArtifactService:
    kwargs.setdefault("policy_dir", POLICY)
    kwargs.setdefault("allow_ephemeral_keys", True)
    return ArtifactService(root=root, **kwargs)
