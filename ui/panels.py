"""Panel dùng chung giữa chat app và Timeline explorer (FR-2, D-27):
text version + cửa sổ hiệu lực + badge + timeline slider + graph 1-hop + link gốc.
"""
from __future__ import annotations

import os

import streamlit as st

try:
    from ui import api_client as api
except ImportError:  # pragma: no cover
    import api_client as api  # type: ignore

PUBLIC_API = os.getenv("PUBLIC_API_URL", "/api")  # link mở từ BROWSER (qua Caddy)

STATUS_BADGE = {"active": "🟢 đang hiệu lực", "suspended": "⏸ NGƯNG hiệu lực",
                "repealed": "⛔ hết hiệu lực"}


def graph_pyvis_or_table(gr: dict) -> None:
    """Graph render pyvis; import fail hay lỗi render → bảng (D-42)."""
    nodes, edges = gr.get("nodes", []), gr.get("edges", [])
    if not edges:
        st.caption("Không có edge trong phạm vi quyền xem.")
        return
    try:
        from pyvis.network import Network

        net = Network(height="360px", width="100%", directed=True, cdn_resources="in_line")
        known = set()
        for n in nodes:
            net.add_node(str(n["node_id"]), label=f"{n['doc_key']}\n{n['path']}",
                         color="#e4572e" if n.get("is_center") else "#4c9be8", shape="box")
            known.add(str(n["node_id"]))
        norm_names = {str(nm["id"]): nm["topic"] for nm in gr.get("norms", [])}
        for e in edges:
            dst = e.get("dst_node") or e.get("dst_norm") or e.get("frontier_ref") \
                or f"unresolved:{str(e['id'])[:6]}"
            dst = str(dst)
            for end, shape in ((str(e["src_node"]), "box"), (dst, "ellipse")):
                if end not in known:
                    label = norm_names.get(end, end if len(end) < 24 else end[:21] + "…")
                    net.add_node(end, label=label, color="#bbbbbb", shape=shape)
                    known.add(end)
            net.add_edge(str(e["src_node"]), dst, label=e["kind"], arrows="to")
        st.components.v1.html(net.generate_html(notebook=False), height=380, scrolling=True)
    except Exception:
        st.dataframe([{"kind": e["kind"], "hướng": e.get("direction"),
                       "citation": e.get("raw_citation"), "confidence": e.get("confidence")}
                      for e in edges], use_container_width=True, hide_index=True)


def render_citation_panel(basis: dict, role: str) -> None:
    """basis: dict Basis (từ Answer) HOẶC {'node_id': ...}/{'doc_key','path'} trực tiếp."""
    key = str(basis.get("node_id") or "")
    if not key and basis.get("doc_key") and basis.get("path"):
        key = f"{basis['doc_key']}~{basis['path']}"
    if not key:
        st.info("Căn cứ này không ghim node (chỉ có trích dẫn văn bản).")
        return
    r = api.get(f"/v1/nodes/{key}/timeline", role)
    if r.status_code != 200:
        st.error(f"Không tải được timeline ({r.status_code}): {api.err_text(r)}")
        return
    t = r.json()
    st.markdown(f"**{t['doc_key']} · `{t['path']}`** — {t.get('heading') or ''}")

    versions = t.get("versions", [])
    if versions:
        labels = [f"v{v['version']} · {v['status']} · {v['valid_from']} → {v['valid_to'] or 'nay'}"
                  for v in versions]
        default = labels[-1]
        for v, lbl in zip(versions, labels):
            if basis.get("version") == v["version"]:
                default = lbl
        sel = st.select_slider("🕰 Timeline phiên bản (kéo để time-travel)", options=labels, value=default)
        v = versions[labels.index(sel)]
        badge = STATUS_BADGE.get(v["status"], v["status"])
        st.markdown(f"{badge} — **hiệu lực từ {v['valid_from']}** đến {v['valid_to'] or 'nay'}"
                    + (" · **chưa từng có bản active**" if v.get("never_active") else ""))
        st.markdown(f"> {v.get('body') or '(trống)'}")
        if v.get("provenance"):
            st.caption("Phả hệ op: " + " → ".join(
                f"{p['kind']} ({p.get('source_doc_key')}, ✍ "
                f"{p.get('ratified_by') or ('lô: ' + str(p.get('batch_approved_by')))})"
                for p in v["provenance"]))
        if v.get("diff_from_prev"):
            with st.expander("Diff với phiên bản trước"):
                st.code(v["diff_from_prev"], language="diff")
    else:
        st.caption(t.get("note") or "Chưa có version nào được compile.")

    for band in t.get("suspensions", []):
        st.warning(f"⏸ Dải treo: {band['valid_from']} → {band['valid_to'] or 'khi sự kiện xảy ra'}"
                   + (f" — chờ: “{band['event_predicate']}” ({band['event_status']})"
                      if band.get("event_predicate") else ""))

    st.markdown("**🕸 Graph 1-hop (edge có kiểu)**")
    g = api.get(f"/v1/nodes/{key}/graph", role, depth=1)
    if g.status_code == 200:
        graph_pyvis_or_table(g.json())
    else:
        st.caption(f"(graph {g.status_code})")
    st.link_button("📄 Văn bản gốc (L0)", f"{PUBLIC_API}/v1/artifacts/{t['doc_key']}")
