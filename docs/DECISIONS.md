# Quyết định kỹ thuật

Mỗi quyết định ghi: ngày, ai quyết, nội dung, lý do, phương án đã cân nhắc. Không sửa quyết định cũ;
quyết định thay thế thì ghi mục mới và trỏ về mục cũ.

## D-001: Cloudflare Workers Paid, dùng chung tài khoản với travienphi

- Ngày: 2026-11-12. Chủ dự án chốt lúc 13:45.
- Nội dung: dùng gói Workers Paid (5 USD/tháng) ngay từ đầu, trên cùng tài khoản Cloudflare với
  travienphi.
- Lý do:
  - D1 gói Free chỉ cho 100.000 dòng ghi mỗi ngày và báo lỗi khi vượt; gói Paid cho 50 triệu dòng
    ghi mỗi tháng và 5 GB dung lượng ([D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/),
    tra ngày 2026-11-12).
  - Bảng lương toàn quốc ước tính 1–4 triệu ô cho một năm học (`REUSE_AUDIT.md` §10). Ở gói Free,
    travienphi đã phải dựng cơ chế nạp A/B kéo dài nhiều ngày.
  - Phí tính theo tài khoản, nên dùng chung thì một khoản 5 USD phủ cả hai site.
- Hệ quả: hai site chia nhau hạn mức của tài khoản. Cảnh báo ở Công đoạn 9 phải tính cả mức dùng của
  travienphi. Nếu travienphi hạ về gói Free theo kế hoạch cũ, site này cũng mất gói Paid; cần báo
  chủ dự án trước khi hạ gói.
- Phương án đã cân nhắc: gói Free kèm ma trận lương lưu dạng JSON (rẻ hơn 5 USD nhưng phức tạp, nạp
  chậm); tài khoản riêng (tách tiền và quyền, thêm 5 USD).

## D-002: Tên miền và tên site để sau, không gắn chữ "teacher"

- Ngày: 2026-11-12. Chủ dự án chốt.
- Nội dung: Công đoạn 1 deploy trên địa chỉ `*.workers.dev`; bước gắn tên miền làm khi chủ dự án
  chọn tên. Tên không chứa "teacher" để mở sang nghề khác ở Công đoạn 10.
- Hệ quả: trước khi có tên miền, site để `noindex` toàn bộ.

## D-003: Pipeline viết bằng Python, chạy trên GitHub Actions

- Ngày: 2026-11-12. Claude quyết theo ủy quyền của chủ dự án.
- Nội dung: thư mục `/pipeline` là package Python 3.12, quản lý bằng uv, kiểm tra bằng ruff, mypy
  strict, pytest. Pipeline ghi vào D1 qua API của Cloudflare và lưu tài liệu gốc vào R2.
- Lý do: dùng lại được bộ tải lịch sự, robots.txt (RFC 9309), các extractor PDF/Excel/Word/HTML và
  kiểm thử của travienphi (`REUSE_AUDIT.md` §8). Hệ sinh thái đọc PDF của Python mạnh hơn JavaScript.
- Phương án đã cân nhắc: TypeScript cho cả repo (một ngôn ngữ, nhưng mất phần dùng lại và phải làm
  lại các xử lý lỗi PDF).

## D-004: Web chạy trên Cloudflare Workers kèm static assets, viết bằng TypeScript

- Ngày: 2026-11-12. Claude quyết theo ủy quyền của chủ dự án.
- Nội dung:
  - `/apps/web` là một Worker TypeScript, định tuyến bằng Hono, HTML render phía server bằng helper
    `html` của Hono (tự escape). Tệp tĩnh (CSS, JS máy tính lương) phục vụ qua static assets.
  - Kiểm thử bằng Vitest với `@cloudflare/vitest-pool-workers`, chạy trên runtime Workers và D1 cục bộ.
  - Deploy bằng wrangler từ GitHub Actions; mỗi pull request có URL xem trước.
- Lý do:
  - Theo tài liệu Cloudflare, Workers có nhiều tính năng hơn Pages và cũng hỗ trợ URL xem trước
    ([compatibility matrix](https://developers.cloudflare.com/workers/static-assets/compatibility-matrix),
    tra ngày 2026-11-12).
  - travienphi dùng JavaScript thuần trong một tệp 2.627 dòng; TypeScript và bộ định tuyến giúp tách
    tệp và bắt lỗi kiểu với kết quả D1.
  - Hono nhỏ, chạy gốc trên Workers. Helper `html` tự escape, thay hàm `esc()` viết tay của travienphi.
- Phương án đã cân nhắc: Pages Functions như travienphi; JavaScript thuần không framework; framework
  đầy đủ (Astro, Remix) bị loại vì thêm bước build và vượt nhu cầu của trang render từ D1.
- Cần kiểm tra ở Công đoạn 1: cách wrangler tạo URL xem trước cho từng PR và cách trỏ bản xem trước
  vào D1 preview.

## D-005: Tài liệu gốc lưu ở R2, không dùng GitHub Release

- Ngày: 2026-11-12. Claude quyết, theo PLAN Công đoạn 1.
- Nội dung: mỗi tài liệu tải về lưu một lần vào R2 với khóa theo SHA-256; D1 lưu `r2_key`.
- Lý do: travienphi lưu trong GitHub Release, phải khôi phục toàn bộ Release ở mỗi lần chạy và từng
  gặp sự cố API liệt kê thiếu Release (biên bản 2026-10-22). R2 truy cập trực tiếp theo khóa.

## D-006: Một repo, hai phần độc lập

- Ngày: 2026-11-12. Claude quyết.
- Nội dung: `/apps/web` (npm workspace) và `/pipeline` (Python) chung một repo. `/packages/db` chứa
  migration SQL dùng chung cho cả hai, chạy bằng `wrangler d1 migrations`.
- Lý do: schema là hợp đồng giữa pipeline và web; để chung chỗ thì một PR đổi schema đổi cả hai bên.

## D-007: Hạ tầng của Công đoạn 1

- Ngày: 2026-11-12. Claude quyết.
- **Bản xem trước:** một Worker riêng `pay-schedules-preview` gắn CSDL `pay-schedules-preview`. Mỗi
  pull request tải lên một phiên bản với `--preview-alias pr-<số>`, nên mỗi PR có URL riêng mà không
  chạm CSDL production. Cờ `--preview-alias` đã kiểm bằng `wrangler versions upload --help`
  (wrangler 4.160.1).
- **R2 dùng chung một bucket** `pay-schedules-docs` cho cả hai môi trường, đúng PLAN (một bucket). Web
  không ghi vào R2; chỉ pipeline ghi. Nếu sau này web cần ghi R2 thì tách bucket preview.
- **Vị trí dữ liệu:** D1 và R2 tạo với gợi ý `enam` (miền đông Bắc Mỹ), vì người dùng ở Mỹ.
- **Tạo tài nguyên bằng workflow** `bootstrap-cloudflare.yml` (chạy tay, chạy lại an toàn) thay vì
  thao tác trên bảng điều khiển, để có dấu vết. ID của CSDL ghi vào `wrangler.jsonc` qua PR. Khi còn
  ID giữ chỗ, `deploy.yml` bỏ qua bước deploy kèm cảnh báo.
- **Cache:** Worker trả `Cache-Control`. Cache API của Workers không hoạt động trên `*.workers.dev`,
  nên cache ở edge (và xóa cache khi publish) làm ở Công đoạn 6, sau khi có tên miền.

## D-008: Công cụ của web

- Ngày: 2026-11-12. Claude quyết.
- Biome 2.6 cho lint và format (một công cụ, không cần ESLint + Prettier).
- Vitest 5 với `@cloudflare/vitest-plugin` 1.8: test chạy trong runtime Workers, D1 cục bộ, migration
  thật của repo được áp trước mỗi tệp test. Gói cũ `@cloudflare/vitest-pool-workers` đã đổi tên
  thành gói này và không còn cập nhật.
- TypeScript 7.0.

## D-009: Mang module "Giữ" sang theo nhu cầu của từng công đoạn

- Ngày: 2026-11-12. Claude quyết.
- Công đoạn 1 chép `robots.py` và `policy.py` (kèm kiểm thử), vì không phụ thuộc gì và là nền của
  mọi lần tải. Các extractor được đánh dấu "Giữ" (`base.py`, `html_table.py`, `excel.py`, `xls.py`,
  `docx_table.py`, `csv_extractor.py`) phụ thuộc mô hình dữ liệu của travienphi; chúng được chép ở
  Công đoạn 4 hoặc 5, khi mô hình dữ liệu mới đã có, để không mang mã chết vào repo.
- Mẫu ý tưởng `test_repo_consistency.py` được viết lại cho repo này ngay từ Công đoạn 1.

## D-010: Commit đầu tiên đẩy thẳng lên `main`

- Ngày: 2026-11-12. Claude quyết.
- Repo mới rỗng nên pull request cần một nhánh gốc. Commit đầu chỉ gồm `README.md`, `docs/`,
  `.gitignore` và `bootstrap-cloudflare.yml`. Workflow này phải nằm sẵn trên `main` vì GitHub chỉ cho
  chạy tay workflow có trên nhánh mặc định; nó không đọc mã nào của repo. Toàn bộ mã còn lại của
  Công đoạn 1 đi qua pull request.
