#!/usr/bin/env python3
"""Method 2 (independent of count_grammar): sequence-validated recount.

Splits each document into Điều blocks, collects khoản/điểm/tiết labels, and
validates numbering sequences (khoản 1,2,3…; điểm theo bảng chữ cái tiếng Việt
a,b,c,d,đ,e,g,h,i,k,l,m,n,o,p…; tiết i,ii,iii…). A count is only trusted when
the sequence is gapless; anomalies are printed for hand inspection.
"""
import re, sys, unicodedata

VN_ALPHA = ['a', 'b', 'c', 'd', 'đ', 'e', 'g', 'h', 'i', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'x', 'y']
ROMAN = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii', 'xiii', 'xiv', 'xv']

RE_DIEU = re.compile(r'^Điều\s+(\d+[a-zđ]?)\s*[\.:]')
RE_KHOAN = re.compile(r'^(\d+[a-zđ]?)\.(\s|$)')
RE_DIEM = re.compile(r'^([a-zđ][0-9]?)\)')
RE_TIET = re.compile(r'^\(([ivx]+)\)')
RE_EXIT = re.compile(r'^(Nơi nhận|XÁC THỰC|KT\.|TL\.|TM\.|CHỦ TỊCH|NGÂN HÀNG NHÀ NƯỚC|ĐẠI DIỆN|\[\d+\]\s|Phụ\s*lục|PHỤ LỤC|Mục\s+\d|Chương\s+[IVX]|CHƯƠNG\s+[IVX])')


def blocks(text):
    depth = 0
    cur = None
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line == '(...)':
            continue
        starts_open = line.startswith('“') or line.startswith("''")
        if depth == 0 and not starts_open:
            m = RE_DIEU.match(line)
            if m:
                cur = m.group(1)
                out.setdefault(cur, {'khoan': [], 'diem': [], 'tiet': []})
            elif RE_EXIT.match(line):
                cur = None
            elif cur:
                if RE_KHOAN.match(line):
                    out[cur]['khoan'].append(RE_KHOAN.match(line).group(1))
                elif RE_DIEM.match(line):
                    out[cur]['diem'].append(RE_DIEM.match(line).group(1))
                elif RE_TIET.match(line):
                    out[cur]['tiet'].append(RE_TIET.match(line).group(1))
        if line.startswith("''"):
            depth += 1
        for ch in line:
            if ch == '“':
                depth += 1
            elif ch == '”':
                depth = max(0, depth - 1)
        if line.endswith("''") and depth > 0:
            depth -= 1
    return out


def check_khoan_seq(labels):
    """khoản: 1,2,3… with optional inserted suffixes (1a.) after their base."""
    anomalies = []
    expect = 1
    for lab in labels:
        m = re.fullmatch(r'(\d+)([a-zđ]?)', lab)
        base, suf = int(m.group(1)), m.group(2)
        if suf:
            if base != expect - 1:
                anomalies.append(f'khoản {lab} sau {expect - 1}')
        elif base == expect:
            expect += 1
        else:
            anomalies.append(f'khoản {lab} (chờ {expect})')
            expect = base + 1
    return anomalies


def check_alpha_seq(labels, alphabet):
    anomalies = []
    idx = 0
    for lab in labels:
        base = re.fullmatch(r'([a-zđ]+)[0-9]?', lab)
        b = base.group(1) if base else lab
        if b in alphabet:
            j = alphabet.index(b)
            if j == 0:
                idx = 1
            elif j == idx:
                idx += 1
            else:
                anomalies.append(f'{lab} (chờ {alphabet[idx] if idx < len(alphabet) else "?"})')
                idx = j + 1
        else:
            anomalies.append(f'{lab} ngoài bảng')
    return anomalies


def audit(path):
    text = unicodedata.normalize('NFC', open(path, encoding='utf-8').read())
    out = blocks(text)
    total = {'dieu': len(out), 'khoan': 0, 'diem': 0, 'tiet': 0}
    anomalies = []
    for dieu, d in out.items():
        total['khoan'] += len(d['khoan'])
        total['diem'] += len(d['diem'])
        total['tiet'] += len(d['tiet'])
        for a in check_khoan_seq(d['khoan']):
            anomalies.append(f'Điều {dieu}: {a}')
        # điểm restart per khoản is unknown from flat scan: validate per contiguous run
        run = []
        for lab in d['diem'] + ['<END>']:
            b = lab[0] if lab != '<END>' else None
            if lab == '<END>' or (run and b == 'a'):
                for a in check_alpha_seq(run, VN_ALPHA):
                    anomalies.append(f'Điều {dieu}: điểm {a}')
                run = []
            if lab != '<END>':
                run.append(lab)
        run = []
        for lab in d['tiet'] + ['<END>']:
            if lab == '<END>' or (run and lab == 'i'):
                for a in check_alpha_seq(run, ROMAN):
                    anomalies.append(f'Điều {dieu}: tiết {a}')
                run = []
            if lab != '<END>':
                run.append(lab)
    return total, anomalies


if __name__ == '__main__':
    for path in sys.argv[1:]:
        total, anomalies = audit(path)
        name = path.split('/')[-1]
        print(f"{name:36s} dieu={total['dieu']:3d} khoan={total['khoan']:3d} "
              f"diem={total['diem']:3d} tiet={total['tiet']:3d}"
              f"  anomalies={len(anomalies)}")
        for a in anomalies:
            print(f'    !! {a}')
