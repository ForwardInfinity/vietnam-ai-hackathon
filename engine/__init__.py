"""Engine hiệu lực (F4) — fold pure + snapshot/sweep/oracle/blast-radius. API: engine/README.md."""
from engine.fold import (active_intervals, ever_active, fold_corpus, materialize_at,
                         state_digest, verify_tiling)
from engine.model import (ArtifactInput, ConflictCertificate, CorpusFold, NodeInput,
                          PendingWindow, Version)
from engine.scope import applicability_matches, scope_hash

__all__ = [
    "ArtifactInput", "ConflictCertificate", "CorpusFold", "NodeInput", "PendingWindow",
    "Version", "active_intervals", "applicability_matches", "ever_active", "fold_corpus",
    "materialize_at", "scope_hash", "state_digest", "verify_tiling",
]
