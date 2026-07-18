#!/usr/bin/env python3
"""Grammar-based structure counter (method 1 of the two independent counts).

Counts Điều/Khoản/Điểm/Tiết/Phụ lục nodes of the DOCUMENT itself per 02-DOMAIN-SPEC §1.
Rules:
- Text quoted inside amendment provisions (“…”, and the '' transcription variant)
  belongs to the quoting node's body and is NOT counted as document structure.
- khoản/điểm/tiết are counted only inside Điều context (numbered enumerations in
  preambles/VBHN headers are not khoản; Phụ lục content is a blob per D-49).
"""
import re, sys, unicodedata

RE_DIEU = re.compile(r'^Điều\s+\d+[a-zđ]?\s*[\.:]')
RE_KHOAN = re.compile(r'^\d+[a-zđ]?\.\s')
RE_DIEM = re.compile(r'^[a-zđ][0-9]?\)')  # no trailing \s: transcriptions glue "đ)Thông tư"
RE_TIET = re.compile(r'^\(?([ivx]+)\)')
RE_PHULUC = re.compile(r'^phụ\s*lục\s*([0-9ivx]+)?\b', re.IGNORECASE)
RE_MUC = re.compile(r'^Mục\s+\d+')
RE_CHUONG = re.compile(r'^(Chương|CHƯƠNG)\s+[IVXLCDM]+')
RE_EXIT = re.compile(r'^(Nơi nhận|XÁC THỰC|KT\.|TL\.|TM\.|CHỦ TỊCH|NGÂN HÀNG NHÀ NƯỚC|ĐẠI DIỆN|\[\d+\]\s)')


def count(text: str) -> dict:
    text = unicodedata.normalize('NFC', text)
    c = {'dieu': 0, 'khoan': 0, 'diem': 0, 'tiet': 0, 'phuluc': 0, 'muc': 0, 'chuong': 0}
    depth = 0
    in_dieu = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line == '(...)':
            continue
        starts_with_open = line.startswith('“') or line.startswith("''")
        if depth == 0 and not starts_with_open:
            if RE_DIEU.match(line):
                c['dieu'] += 1
                in_dieu = True
            elif RE_PHULUC.match(line):
                c['phuluc'] += 1
                in_dieu = False
            elif RE_MUC.match(line):
                c['muc'] += 1
                in_dieu = False
            elif RE_CHUONG.match(line):
                c['chuong'] += 1
                in_dieu = False
            elif RE_EXIT.match(line):
                in_dieu = False
            elif in_dieu and RE_KHOAN.match(line):
                c['khoan'] += 1
            elif in_dieu and RE_DIEM.match(line):
                c['diem'] += 1
            elif in_dieu and RE_TIET.match(line):
                c['tiet'] += 1
        # '' is a transcription variant of “/” seen in TT26: only line-start (open)
        # and line-end (close) occurrences delimit quotes; mid-line pairs are literals
        if line.startswith("''"):
            depth += 1
        for ch in line:
            if ch == '“':
                depth += 1
            elif ch == '”':
                depth = max(0, depth - 1)
        if line.endswith("''") and depth > 0:
            depth -= 1
    return c


if __name__ == '__main__':
    for path in sys.argv[1:]:
        text = open(path, encoding='utf-8').read()
        c = count(text)
        print(f"{path.split('/')[-1]:36s} dieu={c['dieu']:3d} khoan={c['khoan']:3d} "
              f"diem={c['diem']:3d} tiet={c['tiet']:3d} phuluc={c['phuluc']} "
              f"muc={c['muc']} chuong={c['chuong']}")
