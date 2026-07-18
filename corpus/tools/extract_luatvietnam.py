#!/usr/bin/env python3
"""Extract clean UTF-8 NFC text from a luatvietnam.vn document page.

Usage: extract_luatvietnam.py <source.html> [out.txt]
Emits one line per block element (paragraph); keeps Điều/Khoản/Điểm line structure.
"""
import sys, re, unicodedata
from bs4 import BeautifulSoup, Tag

JUNK_CLASSES = {
    'item-status', 'bg-theo-doi', 'bg_phantich', 'btn-doc', 'doc-so-sanhvb',
    'tooltip-1', 'tooltip-content-1', 'item-tools-hd', 'row-menu1', 'the-article-tools',
    'lv-ads', 'box-maps', 'social-share', 'banner', 'breadcrumb', 'docitem-binhluan',
    'docitemadd',
}
JUNK_LINES = {
    'Phân tích', 'Đang theo dõi', 'Theo dõi', 'Đã biết', 'Tình trạng hiệu lực:',
    'Hiệu lực: Đã biết', 'Tình trạng hiệu lực: Đã biết', 'Xem chi tiết', 'In lược đồ',
    'Phân tích văn bản', 'Lưu', 'Báo lỗi', 'Gửi', 'LuatVietnam.vn',
    'Văn bản này có phụ lục đính kèm. Tải về để xem toàn bộ nội dung.',
}
BLOCK = {'p', 'div', 'td', 'th', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'}


def norm_line(s: str) -> str:
    s = unicodedata.normalize('NFC', s)
    s = s.replace('\u00a0', ' ').replace('\u200b', '')
    return ' '.join(s.split())


def is_leaf_block(el: Tag) -> bool:
    if el.name not in BLOCK:
        return False
    return not any(isinstance(c, Tag) and c.name in BLOCK for c in el.descendants)


def extract(html: str) -> str:
    soup = BeautifulSoup(html, 'lxml')
    root = soup.find('div', class_='tab-noi-dung')
    if root is None:
        cands = [d for d in soup.find_all('div') if 'Căn cứ' in d.get_text()]
        root = min(cands, key=lambda d: len(d.get_text())) if cands else soup
    for el in list(root.find_all(True)):
        if el.attrs is None or el.parent is None:
            continue
        if el.name in ('script', 'style', 'svg', 'img', 'button', 'input', 'form'):
            el.decompose()
            continue
        cls = set(el.get('class') or [])
        if cls & JUNK_CLASSES:
            el.decompose()
    for br in root.find_all('br'):
        br.replace_with('\n')
    lines = []
    for el in root.find_all(True):
        if not is_leaf_block(el):
            continue
        for raw in el.get_text('').split('\n'):
            t = norm_line(raw)
            if not t or t in JUNK_LINES:
                continue
            if re.fullmatch(r'[_\-–—.=*\s]+', t):
                continue
            lines.append(t)
    out, prev = [], None
    for t in lines:
        if t == prev and len(t) < 60:
            continue
        out.append(t)
        prev = t
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    src = sys.argv[1]
    html = open(src, encoding='utf-8', errors='replace').read()
    text = extract(html)
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w', encoding='utf-8').write(text)
        print(f'{sys.argv[2]}: {len(text)} chars, {text.count(chr(10))} lines')
    else:
        sys.stdout.write(text)
