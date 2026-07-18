#!/usr/bin/env python3
"""Build corpus/text/*.txt from raw HTML: full docs verbatim, excerpts by line ranges.

Excerpt ranges refer to line numbers (1-based, inclusive) of the full extraction
of the same raw HTML; elisions are marked with a standalone "(...)" line.
Re-runnable: deterministic output.
"""
import pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent
sys.path.insert(0, str(HERE))
from extract_luatvietnam import extract  # noqa: E402

FULL = [
    'tt-39-2016-tt-nhnn', 'tt-06-2023-tt-nhnn', 'tt-10-2023-tt-nhnn',
    'tt-12-2024-tt-nhnn', 'nq-01-2019-nq-hdtp', 'tt-26-2022-tt-nhnn',
    'tt-52-2025-tt-nhnn', 'qd-4033-2025-dinh-chinh',
    'vbhn-21-2024-tt39', 'vbhn-06-2026-tt39',
]

# luatvietnam inline annotation leaks (content of OTHER documents rendered inline,
# verified against VBHN 21/2024 + original structure) — dropped by exact match
DROP_LINES = {
    'tt-39-2016-tt-nhnn': [
        '(iv) Đối với các khoản cho vay có mức giá trị nhỏ, có biện pháp kiểm tra, giám sát việc sử dụng vốn vay đúng mục đích đã cam kết và trả nợ của khách hàng, đảm bảo khả năng thu hồi nợ gốc và lãi tiền vay đầy đủ, đúng hạn theo thỏa thuận.',
    ],
}


# D-43 transcription repair: closing ” of the k2 Điều 24 TT22 quote block is missing
# on luatvietnam; the gốc quote must close before khoản 3 Điều 24 (suffix is unique).
SUFFIX_PATCHES = {
    'tt-22-2019-tt-nhnn-trich': [
        ('giai đoạn 2016- 2020”.', 'giai đoạn 2016- 2020”.”.'),
    ],
}


def postprocess(slug: str, text: str) -> str:
    drops = set(DROP_LINES.get(slug, []))
    lines = [l for l in text.splitlines() if l not in drops]
    if slug == 'vbhn-21-2024-tt39':
        # footnote superscript glued to khoản number ("12.6 Cho vay", "1.21Căn cứ");
        # insert the space the source itself uses elsewhere ("8. 13 Để ...")
        lines = [re.sub(r'^(\d+[a-zđ]?)\.(\d+)(?=\s|[^\d\s.])', r'\1. \2 ', l) for l in lines]
    if slug == 'vbhn-06-2026-tt39':
        # footnote rendered between khoản number and dot ("5 [42] . Cho vay ...")
        lines = [re.sub(r'^(\d+[a-zđ]?)\s+(\[\d+\])\s*\.\s*', r'\1. \2 ', l) for l in lines]
    out = []
    i = 0
    while i < len(lines):
        # transcription artifact: khoản number split from its body ("1." alone)
        if re.fullmatch(r'\d+[a-zđ]?\.', lines[i]) and i + 1 < len(lines):
            out.append(lines[i] + ' ' + lines[i + 1])
            i += 2
        else:
            out.append(lines[i])
            i += 1
    for old_suffix, new_suffix in SUFFIX_PATCHES.get(slug, []):
        hits = [j for j, l in enumerate(out) if l.endswith(old_suffix)]
        assert len(hits) == 1, f'{slug}: suffix patch matched {len(hits)} lines'
        out[hits[0]] = out[hits[0]][:-len(old_suffix)] + new_suffix
    return '\n'.join(out) + '\n'


# slug -> list of (start, end) inclusive line ranges of the full extraction
EXCERPTS = {
    'blds-91-2015-qh13-trich': [(1, 8), (1244, 1245), (1895, 1896), (2019, 2053), (2957, 2972)],
    'luat-47-2010-qh12-trich': [(1, 75), (785, 827), (1011, 1039), (1217, 1232)],
    'luat-32-2024-qh15-trich': [(1, 91), (948, 982), (1219, 1256), (1868, 1900)],
    'tt-41-2016-tt-nhnn-trich': [(1, 22), (23, 133), (192, 214), (527, 538), (601, 616), (995, 1038)],
    'tt-22-2019-tt-nhnn-trich': [(1, 36), (37, 117), (159, 200), (372, 396), (397, 439)],
}


def build():
    out_dir = CORPUS / 'text'
    out_dir.mkdir(exist_ok=True)
    for slug in FULL:
        html = (CORPUS / 'raw' / slug / 'source.html').read_text(encoding='utf-8', errors='replace')
        text = postprocess(slug, extract(html))
        (out_dir / f'{slug}.txt').write_text(text, encoding='utf-8')
        print(f'{slug}: full, {len(text.splitlines())} lines')
    for slug, ranges in EXCERPTS.items():
        html = (CORPUS / 'raw' / slug / 'source.html').read_text(encoding='utf-8', errors='replace')
        lines = postprocess(slug, extract(html)).splitlines()
        parts, prev_end = [], 0
        for start, end in ranges:
            assert start <= end <= len(lines), f'{slug}: bad range {start}-{end} (have {len(lines)})'
            if parts and start > prev_end + 1:
                parts.append('(...)')
            parts.extend(lines[start - 1:end])
            prev_end = end
        text = '\n'.join(parts) + '\n'
        (out_dir / f'{slug}.txt').write_text(text, encoding='utf-8')
        print(f'{slug}: excerpt, {len(parts)} lines')


if __name__ == '__main__':
    build()
