# LawState — SHB hackathon

Máy tính hiệu lực pháp quy ngân hàng ba trục thời gian (ban hành / hiệu lực / biết-đến K),
retrieval trên trạng thái đã compile, verifier hai tầng. **LLM đề xuất — người phê chuẩn —
engine tất định thực thi.**

- **Demo:** https://152-42-242-127.sslip.io (chat `/`, API docs `/api/docs`, health `/health`, admin `/admin`)
- **Spec:** `docs/` (00 vision · 01 quyết định đã khóa · 02 domain · 03 system · 04 corpus/eval · 05 demo)
- **Contracts cho dev song song:** `CONTRACTS.md`
- **Dev:** `cp .env.example .env` điền key → `make smoke` (gate merge) · `make test` · `make up`

Mọi commit lên `master` tự deploy lên VPS qua GitHub Actions (test xanh mới deploy).
