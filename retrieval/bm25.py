"""BM25 in-process trên snapshot (D-28, D-39, S1).

Tokenize: pyvi ViTokenizer (fallback tách whitespace khi thiếu pyvi). Số hiệu văn
bản được BẢO VỆ thành MỘT token bằng regex TRƯỚC khi tách từ — kể cả dạng lỗi
khoảng trắng ngay trong bản gốc (`32 /2026/TT- NHNN` → token `32/2026/tt-nhnn`,
bẫy 02 §7.2: BM25 mù nếu số hiệu bị tách rời).

Index rebuild từ snapshot mỗi lần ingest — corpus vài nghìn node, <1s (D-39).
"""
from __future__ import annotations

import re
import unicodedata

from rank_bm25 import BM25Okapi

try:  # pyvi = CRF word segmenter thuần Python; thiếu → fallback whitespace
    from pyvi import ViTokenizer

    _HAVE_PYVI = True
except Exception:  # pragma: no cover - môi trường thiếu pyvi
    _HAVE_PYVI = False

# Số hiệu văn bản: {số}/{năm}/{loại}[-{cơ quan}]… — chấp nhận khoảng trắng lỗi
# quanh '/' và '-' (bẫy §7.2); IGNORECASE ngầm qua lớp ký tự để câu hỏi viết
# thường vẫn khớp. Ví dụ khớp: 39/2016/TT-NHNN · 34/2016/NĐ-CP · 32/2024/QH15 ·
# 01/2019/NQ-HĐTP · `32 /2026/TT- NHNN` (lỗi khoảng trắng trong bản gốc).
DOC_NUM_RE = re.compile(
    r"(?<![\w/])"
    r"\d{1,4}\s*/\s*\d{4}\s*/\s*"
    r"[A-ZĐa-zđ]{1,8}\d{0,3}(?:\s*-\s*[A-ZĐa-zđ][A-ZĐa-zđ0-9]{0,14})*"
    r"(?![\w/])"
)

_PUNCT_EDGE = re.compile(r"^[\W]+|[\W]+$", re.UNICODE)  # giữ '_' pyvi ghép từ


def canonical_doc_num(raw: str) -> str:
    """`32 /2026/TT- NHNN` → `32/2026/TT-NHNN` (vá khoảng trắng, uppercase)."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", raw)).upper()


def extract_doc_numbers(text: str) -> tuple[str, list[str]]:
    """Tách mọi số hiệu ra khỏi text.

    Trả (text đã thay số hiệu bằng khoảng trắng, [số hiệu canonical]).
    Chạy TRƯỚC word-segment để mỗi số hiệu thành đúng MỘT token.
    """
    found: list[str] = []

    def _repl(m: re.Match[str]) -> str:
        found.append(canonical_doc_num(m.group(0)))
        return " "

    return DOC_NUM_RE.sub(_repl, text), found


def _segment(text: str) -> list[str]:
    if _HAVE_PYVI:
        text = ViTokenizer.tokenize(text)
    return text.split()


def tokenize(text: str) -> list[str]:
    """NFC → bảo vệ số hiệu thành 1 token → pyvi segment phần còn lại → lowercase."""
    text = unicodedata.normalize("NFC", text or "")
    rest, doc_nums = extract_doc_numbers(text)
    tokens = [dn.lower() for dn in doc_nums]
    for tok in _segment(rest):
        tok = _PUNCT_EDGE.sub("", tok)
        if tok:
            tokens.append(tok.lower())
    return tokens


class BM25Index:
    """rank_bm25 in-process trên các entry (key, text) — rebuild <1s (D-39)."""

    def __init__(self, entries: list[tuple[object, str]]):
        self._keys = [k for k, _ in entries]
        token_lists = [tokenize(t) for _, t in entries]
        self._token_sets = [set(ts) for ts in token_lists]
        self._bm25 = BM25Okapi(token_lists) if entries else None

    def search(self, query: str, top_n: int = 30) -> list[tuple[object, float]]:
        """Top-n (key, score) giảm dần, tie-break theo thứ tự corpus (tất định).

        Chỉ trả doc có GIAO TOKEN với query (retrieval floor trung thực) — không
        dùng score>0 vì IDF của BM25Okapi bằng 0 khi term xuất hiện ở đúng nửa
        corpus (df = N/2), doc khớp vẫn phải được tính."""
        if self._bm25 is None:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        q_set = set(q_tokens)
        scores = self._bm25.get_scores(q_tokens)
        matching = [i for i in range(len(scores)) if q_set & self._token_sets[i]]
        matching.sort(key=lambda i: (-scores[i], i))
        return [(self._keys[i], float(scores[i])) for i in matching[:top_n]]
