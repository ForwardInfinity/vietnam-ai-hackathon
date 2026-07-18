"""Registry invariant compliance (S4.8, R-24, D-37 kênh b) — máy dò công nghiệp duy nhất
từng hoạt động: compliance viết invariant THỰC THI ĐƯỢC, chạy trên effective state sau mỗi
run. Fail → conflict tier-3 + notification. Registry enable/disable từng invariant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterator, Mapping
from uuid import UUID

from engine.model import ArtifactInput, NodeInput, Version


@dataclass(frozen=True)
class Violation:
    invariant_id: str
    reason: str
    members: tuple[tuple[UUID, int], ...]      # (node_id, version) — khớp conflict.member_versions


@dataclass
class EffectiveState:
    as_of: date
    versions: Mapping[UUID, tuple[Version, ...]]
    nodes: Mapping[UUID, NodeInput]
    artifacts: Mapping[str, ArtifactInput]

    def active(self) -> Iterator[tuple[NodeInput, ArtifactInput, Version]]:
        for node_id in sorted(self.versions, key=str):
            node = self.nodes.get(node_id)
            if node is None:
                continue
            art = self.artifacts[node.artifact_id]
            for v in self.versions[node_id]:
                if v.status == "active" and v.valid_from <= self.as_of \
                        and (v.valid_to is None or self.as_of < v.valid_to):
                    yield node, art, v


Check = Callable[[EffectiveState], list[Violation]]
_REGISTRY: dict[str, tuple[Check, bool]] = {}


def register(invariant_id: str, check: Check, enabled: bool = True) -> None:
    _REGISTRY[invariant_id] = (check, enabled)


def set_enabled(invariant_id: str, enabled: bool) -> None:
    check, _ = _REGISTRY[invariant_id]
    _REGISTRY[invariant_id] = (check, enabled)


def registered() -> dict[str, bool]:
    return {k: enabled for k, (_, enabled) in sorted(_REGISTRY.items())}


def run_all(state: EffectiveState) -> list[Violation]:
    out: list[Violation] = []
    for invariant_id in sorted(_REGISTRY):
        check, enabled = _REGISTRY[invariant_id]
        if enabled:
            out.extend(check(state))
    return out


def effective_state(cf, nodes, artifacts, as_of: date) -> EffectiveState:
    """Tiện ích: dựng EffectiveState từ CorpusFold + input fold."""
    arts = artifacts if isinstance(artifacts, Mapping) else {a.id: a for a in artifacts}
    return EffectiveState(as_of=as_of, versions=cf.versions,
                          nodes={n.id: n for n in nodes}, artifacts=arts)


# đăng ký 2 invariant mẫu (R-24)
from engine.invariants import inv_comp_01, inv_comp_02  # noqa: E402,F401
