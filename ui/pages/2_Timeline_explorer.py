"""Timeline & Graph explorer (bề mặt #3, #4 của 00-VISION §3; đường D-27).

Tra cứu trực tiếp một điều-khoản-điểm: mọi phiên bản (kể cả treo/chưa-từng-active),
dải treo, phả hệ op, graph citation có kiểu — không cần đi qua câu hỏi chat.
"""
import streamlit as st

try:
    from ui import panels
except ImportError:  # streamlit chạy từ ui/pages — thêm ui/ vào path
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import panels  # type: ignore

st.set_page_config(page_title="LawState — Timeline", page_icon="🕰", layout="wide")
st.title("🕰 Timeline & Graph explorer")
st.caption("Câu bẫy lịch sử demo beat 3: “khoản 8 Điều 8 TT39 đã từng hiệu lực chưa?” "
           "— trả lời bằng dải treo + nhãn *chưa từng có bản active*, không viết lại lịch sử.")

role = st.radio("Quyền xem", ["employee", "customer"], horizontal=True,
                help="INV-12: customer không thấy một byte nào từ văn bản nội bộ")

examples = {
    "TT39 Đ8 k2 (bị TT06 sửa)": "39/2016/TT-NHNN~dieu:8/khoan:2",
    "TT39 Đ8 k8 (TT06 chèn, TT10 treo — chưa từng active)": "39/2016/TT-NHNN~dieu:8/khoan:8",
    "TT39 Đ2 k5 (định nghĩa)": "39/2016/TT-NHNN~dieu:2/khoan:5",
    "QT-TD-01 Đ3 (nội bộ — customer sẽ bị 404)": "QT-TD-01~dieu:3",
}
pick = st.selectbox("Ví dụ nhanh", list(examples))
key = st.text_input("Key (`<doc_key>~<path>` hoặc UUID node)", value=examples[pick])

if key:
    panels.render_citation_panel({"doc_key": key.split("~")[0] if "~" in key else None,
                                  "path": key.split("~", 1)[1] if "~" in key else None,
                                  "node_id": key if "~" not in key else None}, role)
