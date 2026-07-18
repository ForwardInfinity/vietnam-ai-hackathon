"""Script QA `python -m engine.story` phải tự khớp 4/4 (deliverable đối chiếu domain)."""
from engine.story import main


def test_story_all_match(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "CHƯA TỪNG CÓ HIỆU LỰC" in out
    assert "Tổng: 4/4 câu chuyện khớp." in out
    assert "LỆCH ✗" not in out
