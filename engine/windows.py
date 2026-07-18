"""PASS 1 — resolve cửa sổ hiệu lực của TỪNG OP trước khi fold (S4.5, D-10, D-11).

- `close_window(target_op)`: đặt valid_to = close.valid_from cho op đích (đóng treo-theo-sự-kiện).
- `repeal(target_op)`:       window_end = min(end, repeal.valid_from) — CHỈ từ đó trở đi;
                             cửa sổ đã qua BẤT KHẢ XÂM PHẠM (INV-5).
- `valid_to_event` chưa có close_window ratified → cửa sổ MỞ VÔ HẠN; pending_event giữ nghĩa vụ.

Giới hạn v1 (ghi nhận): op-sửa-op chỉ resolve MỘT tầng — repeal một op close_window/repeal
khác không hồi phục hiệu lực của op bị đóng (chưa có ca trong corpus; sẽ nâng khi có).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Sequence
from uuid import UUID

from engine.model import PendingWindow, as_utc_ts, sv


@dataclass(frozen=True)
class Window:
    start: date
    end: date | None              # None = mở vô hạn


def min_end(a: date | None, b: date | None) -> date | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def eligible_ops(ops: Iterable[Any], k_cutoff: datetime | None = None) -> list[Any]:
    """Op tham gia fold: đã ratify, ingested_at <= K (D-02, R-2).
    Op superseded (D-20) vẫn là chân lý tại K nếu op đè nó ingested SAU K."""
    by_id = {o.id: o for o in ops if o.id is not None}
    k_ts = as_utc_ts(k_cutoff) if k_cutoff is not None else None
    out = []
    for o in ops:
        status = sv(o.status)
        if status not in ("ratified", "superseded"):
            continue
        if k_ts is not None and as_utc_ts(o.ingested_at) > k_ts:
            continue
        if status == "superseded":
            if k_ts is None:
                continue                                  # hiện tại: op đè đã thay nó
            successor = by_id.get(o.superseded_by) if o.superseded_by else None
            if successor is None or as_utc_ts(successor.ingested_at) <= k_ts:
                continue                                  # tại K đã thấy op đè → loại
        out.append(o)
    return out


def resolve_windows(
    ops: Sequence[Any],
) -> tuple[dict[UUID, Window], list[Any], list[tuple[UUID, UUID]]]:
    """→ (windows theo op_id, ops treo-theo-sự-kiện còn mở, [(op bị đóng, op đóng)])."""
    modifiers: dict[UUID, list[Any]] = defaultdict(list)
    for o in ops:
        if o.target_op is not None and sv(o.kind) in ("close_window", "repeal"):
            modifiers[o.target_op].append(o)

    windows: dict[UUID, Window] = {}
    closed: list[tuple[UUID, UUID]] = []
    pending: list[Any] = []
    for o in ops:
        if o.valid_from is None:
            continue
        end = o.valid_to
        closer: Any = None
        for m in sorted(modifiers.get(o.id, ()), key=lambda m: (m.valid_from, str(m.id))):
            if m.valid_from is None:
                continue
            new_end = min_end(end, m.valid_from)
            if new_end != end or closer is None:
                closer = m if (end is None or m.valid_from <= end) else closer
            end = new_end
        if end is not None and end < o.valid_from:
            end = o.valid_from                            # forward-only → cửa sổ rỗng, không âm
        windows[o.id] = Window(o.valid_from, end)
        if closer is not None:
            closed.append((o.id, closer.id))
        if o.valid_to_event and end is None:
            pending.append(o)
    return windows, pending, closed


def pending_windows(pending_ops: Sequence[Any]) -> tuple[PendingWindow, ...]:
    return tuple(
        PendingWindow(op_id=o.id, predicate=o.valid_to_event, target_node=o.target_node)
        for o in sorted(pending_ops, key=lambda o: str(o.id))
    )
