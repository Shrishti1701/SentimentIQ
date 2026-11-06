"""Registry identity helpers using the project's canonical deterministic-ID convention."""

from __future__ import annotations

from intelligence.entity_contracts import DeterministicIdFactory


def registry_id(kind: str, payload: dict[str, object]) -> str:
    """Create a canonical registry identifier with an isolated factory ledger."""
    return DeterministicIdFactory().create(f"REGISTRY-{kind}", payload)
