# pay-schedules

Tra cứu bảng lương công khai của học khu công lập ở Mỹ (giai đoạn sau: các đơn vị khu vực công
khác). Mỗi con số kèm link tài liệu gốc. Tên site và tên miền chưa chốt (`docs/DECISIONS.md` D-002).

Kế hoạch: [`docs/PLAN.md`](docs/PLAN.md). Quy tắc làm việc: [`AGENTS.md`](AGENTS.md).

## Cấu trúc

```text
apps/web             Worker (TypeScript, Hono): render trang từ D1
packages/db          migration SQL của D1 và hàm đọc (TypeScript), dùng chung cho web và pipeline
pipeline             Python: discover, fetch, classify, extract, validate, publish
data/seeds           tệp nhập ban đầu (không commit dữ liệu, chỉ README)
docs                 PLAN, DECISIONS, REUSE_AUDIT
.github/workflows    ci.yml, deploy.yml, bootstrap-cloudflare.yml
```

## Chạy cục bộ

Web (Node ≥ 22.12):

```bash
npm ci
npm run lint && npm run typecheck && npm test
cd apps/web && npm run migrate:local && npm run dev
```

Pipeline ([uv](https://docs.astral.sh/uv/)):

```bash
cd pipeline
uv sync
uv run ruff check src tests && uv run mypy && uv run pytest
```

## Hạ tầng Cloudflare

Tài khoản dùng chung với travienphi, gói Workers Paid (D-001). Tài liệu gốc lưu trong GitHub
Release riêng tư của repo, không dùng R2 (D-011).

| Tài nguyên | Production | Preview |
| --- | --- | --- |
| Worker | `pay-schedules` | `pay-schedules-preview`, mỗi PR một alias `pr-<số>` |
| D1 | `pay-schedules` | `pay-schedules-preview` |

Thiết lập một lần:

1. Trong repo GitHub, thêm secret `CLOUDFLARE_API_TOKEN` (quyền tài khoản: Workers Scripts Edit,
   D1 Edit) và biến `CLOUDFLARE_ACCOUNT_ID`. Đã làm ngày 2026-11-12.
2. Chạy workflow **Bootstrap Cloudflare** (Actions → Run workflow). Tóm tắt job in ID của hai CSDL.
3. Ghi hai ID vào `apps/web/wrangler.jsonc` qua pull request. Từ đó `deploy.yml` tạo bản xem trước
   cho mỗi PR và deploy production khi merge vào `main`.
