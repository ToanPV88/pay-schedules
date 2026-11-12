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

## D-011: Tài liệu gốc lưu trong GitHub Release, không dùng R2 (thay D-005 và mục R2 của D-007)

- Ngày: 2026-11-12. Chủ dự án chốt lúc 14:31.
- Bối cảnh: lần chạy đầu của `bootstrap-cloudflare.yml` tạo được hai CSDL D1 nhưng tạo bucket R2 thất
  bại (`Please enable R2 through the Cloudflare Dashboard`, mã 10042). Bật R2 cần đăng ký gói R2
  gắn thẻ thanh toán của tài khoản (miễn phí trong hạn mức, tính tiền khi vượt).
- Nội dung: như travienphi (ADR-0009), mỗi lần chạy pipeline đóng gói các tài liệu **mới** theo
  SHA-256 và đính vào một GitHub Release riêng tư của repo. Không bật R2, không có binding R2 trong
  Worker. Bỏ bước tạo R2 khỏi `bootstrap-cloudflare.yml`.
- Lý do: không thêm đăng ký dịch vụ tính tiền; dung lượng tệp trong Release không tính vào phút
  GitHub Actions.
- Hệ quả, phải xử lý ở các công đoạn sau:
  - Worker không đọc được Release của repo private. Trang công khai chỉ trỏ link gốc của học khu.
    Trang xem tay nội bộ (Công đoạn 5) cần cách khác để hiện PDF cạnh bảng đã trích, ví dụ mở link
    gốc hoặc link Release cho người đã đăng nhập GitHub.
  - Tránh lỗi travienphi đã gặp (khôi phục phải tải mọi Release; API liệt kê Release trả thiếu ngày
    2026-10-22): D1 lưu tên Release và tên tệp của từng tài liệu, để pipeline tải đúng tệp cần,
    không khôi phục toàn bộ.
  - Tải lên và tải về Release tốn phút Actions; 2.000 phút miễn phí mỗi tháng tính chung cho cả tài
    khoản GitHub, chia với các repo khác.
- Token Cloudflare `pay-schedules-github-actions` có thừa quyền R2 Storage Edit. Quyền này vô hại khi
  R2 chưa bật; có thể bỏ khi sửa token lần sau.

## D-012: Schema D1 của Công đoạn 2 (migration 0002) và các chỗ khác PLAN

- Ngày: 2026-11-12. Claude quyết.
- Đã kiểm tra trước khi viết:
  - D1 hỗ trợ FTS5 ([SQL statements](https://developers.cloudflare.com/d1/sql-api/sql-statements/),
    tra ngày 2026-11-12); travienphi cũng đang chạy FTS5 trên D1 thật (`REUSE_AUDIT.md` §1).
  - D1 kiểm tra khóa ngoại mặc định, kể cả trong migration
    ([Foreign keys](https://developers.cloudflare.com/d1/sql-api/foreign-keys/)).
- Giữ đúng PLAN: 12 bảng và cột chính; tên bảng `districts` (đổi tên ở Công đoạn 10 như PLAN);
  `employer_type` mặc định `school_district`, `pay_basis`, `hours_per_year`; bảng không lane;
  tiền là số nguyên cents; nhãn gốc ở `label_raw`.
- Khác PLAN, kèm lý do:
  1. **Khóa duy nhất của `schedules`** chỉ áp cho bảng `published` (chỉ mục duy nhất có điều kiện).
     Nếu áp cho mọi trạng thái, bản trích lại của cùng năm học không lưu được dưới dạng draft trong
     khi bản cũ đang published, nên không có bước "bảng cũ chuyển superseded" của Công đoạn 5.
  2. **`schedule_type` và `employer_type` dùng bảng mã** (`schedule_types`, `employer_types`) thay vì
     CHECK. SQLite không sửa được CHECK nếu không dựng lại bảng; với bảng mã, Công đoạn 10 chỉ cần
     INSERT thêm giá trị.
  3. **`source_documents`:** bỏ `r2_key`, thêm `release_tag` + `asset_name` (D-011). `district_id` cho
     phép NULL vì tệp của bang (CA, KY) phủ nhiều học khu. Thêm `last_seen_at`; khóa duy nhất
     `(url, sha256)`.
  4. **Tiền đều là số nguyên:** `extraction_runs.cost_usd` thành `cost_usd_micros`; cột của
     `district_summary` có hậu tố `_cents`.
  5. **Cột thêm:** `schedules.source_sheet` (nguồn Excel không có số trang), `extraction_run_id`,
     `superseded_by`, `published_at`, `notes`; `stipends.amount_raw` (phụ cấp dạng "2% of base");
     `review_queue.resolution`; `district_summary.schedule_id`, `computed_at`.
- Ràng buộc trong schema (không chỉ trong mã):
  - năm học dạng `YYYY-YY`, hai số sau là năm kế tiếp;
  - ô trống phải có ghi chú;
  - khóa ngoại kép `(step_id, schedule_id)` và `(lane_id, schedule_id)`, nên ô không trỏ được sang
    bậc hay cột của bảng khác;
  - bảng không lane có tối đa một ô mỗi bậc;
  - `published` phải có `published_at`; `superseded` phải có `superseded_by`;
  - sha256 là 64 ký tự hex thường.
- `district_summary` vẫn giữ ba mốc của giáo viên như PLAN (BA bậc 1, MA bậc 10, tối đa). Cách tính
  viết ở Công đoạn 5 (bước Publish).
- `packages/db` là package TypeScript: chứa migration và hàm đọc (`getSchedule`) cho Worker. Pipeline
  Python ghi vào D1 qua API của Cloudflare (Công đoạn 4).
- Tìm kiếm: `districts_fts` (FTS5, bỏ dấu) đồng bộ với `districts` bằng trigger.

## D-013: Claude tự merge pull request khi mọi check xanh

- Ngày: 2026-11-12. Chủ dự án cho phép lúc 14:35.
- Nội dung: Claude được merge PR vào `main` khi mọi workflow chạy cho commit mới nhất của PR đều xanh
  (`skipped` của job chỉ chạy trên `main` được tính là bình thường). Không merge khi có check đỏ,
  đang chạy hoặc chưa chạy. Kiểu merge: squash.

## D-014: Tải tệp nguồn công khai qua workflow, lưu vào GitHub Release

- Ngày: 2026-11-12. Claude quyết.
- Bối cảnh: môi trường làm việc của Claude không ra được nces.ed.gov (proxy chặn), còn máy chạy GitHub
  Actions thì ra được.
- Nội dung:
  - Tệp kê khai `pipeline/sources/*.json` liệt kê đúng các URL được tải. Lệnh
    `pay-pipeline fetch-sources` tải qua `PoliteFetcher` (chép từ travienphi: robots.txt, ≥ 5 giây
    giữa hai yêu cầu cùng host, thử lại có giới hạn, giới hạn kích thước) và ghi `manifest.json`
    (URL, URL cuối, thời điểm tải, SHA-256, kích thước).
  - Workflow `fetch-sources.yml`: job `fetch` (chỉ đọc repo) là job duy nhất ra Internet; job
    `archive` có quyền `contents: write` chỉ để tạo Release `<tiền tố>-<ngày>-<run>`, không ra Internet,
    không dùng secret. Release đã có không bị ghi đè.
  - Workflow nạp kiểm SHA-256 từng tệp theo `manifest.json` trước khi dùng (`pay-pipeline verify-sources`).
- Phụ thuộc mới: `httpx` (bộ tải lịch sự).
- `test_repo_consistency.py` liệt kê rõ các job được ghi repo (`WRITE_JOBS`) và chặn job đó chạy công
  cụ tải hay dùng secret.

## D-015: Danh mục học khu từ NCES CCD 2024-25 (Công đoạn 3)

- Ngày: 2026-11-12. Claude quyết.
- Nguồn (Release `src-nces-ccd-2425-20261112-43179049772`):
  - Danh mục LEA: https://nces.ed.gov/ccd/Data/zip/ccd_lea_029_2425_w_1a_073025.zip
  - Sĩ số LEA: https://nces.ed.gov/ccd/Data/zip/ccd_lea_052_2425_l_1a_073025.zip
  - Vị trí, quận, tọa độ (EDGE): https://nces.ed.gov/programs/edge/data/EDGE_GEOCODE_PUBLICLEA_2425.zip
  - Bảng đối chiếu: https://nces.ed.gov/ccd/tables/202425_summary_2.asp (CCD 2024-25 Final Version 1a,
    cùng phiên bản với tệp danh mục).
- Vì sao 2024-25 mà không phải 2025-26: bản 2025-26 hiện chỉ là danh mục sơ bộ (công bố 7/2026), chưa
  có sĩ số và chưa có bảng tổng hợp để đối chiếu. Khi NCES công bố bản chính thức 2025-26, thêm tệp kê
  khai mới; importer giữ slug cũ theo mã NCES.
- Quy tắc lọc:
  - Chỉ 50 bang + DC (bỏ lãnh thổ và Bureau of Indian Education).
  - Đang hoạt động đầu năm học: `SY_STATUS` ∈ {1 Open, 3 New, 4 Added, 5 Changed, 8 Reopened}. Đây là
    định nghĩa NCES dùng cho "operating districts" (đối chiếu khớp 50/51 bang; dùng `UPDATED_STATUS`
    thì Missouri lệch 1).
  - Loại LEA 1 và 2 ("regular", 2 = thành viên supervisory union). Bỏ supervisory union (3), service
    agency (4), cơ quan bang (5), liên bang (6), charter độc lập (7), khác (8), chuyên biệt (9).
  - **New York City:** 33 học khu con (UNION 300) được gộp vào "NYC Chancellor's Office" (LEAID
    3620580), sĩ số là tổng các học khu con. NCES cũng tính NYC là một LEA trong bảng tổng hợp; giáo
    viên NYC dùng chung một hợp đồng.
- Rủi ro để xem lại ở Công đoạn 5: ở Vermont, Montana và vài nơi ở California, supervisory union có thể
  là đơn vị thương lượng hợp đồng giáo viên. Theo PLAN, supervisory union bị loại; học khu thành viên
  vẫn có trang.
- Cột:
  - sĩ số = "Derived - Education Unit Total minus Adult Education Count" (như bảng tổng hợp NCES);
  - quận và tọa độ lấy từ EDGE;
  - website giữ như NCES, chỉ thêm `http://` khi thiếu;
  - tên giữ nguyên văn NCES (một số bang viết hoa toàn bộ). Cách hiển thị để Công đoạn 6 quyết.
- Slug: `slugify(tên)`; trùng trong bang thì thêm quận, vẫn trùng thì thêm mã NCES. Học khu đã có slug
  giữ nguyên mãi (tra theo mã NCES), kể cả khi đổi tên.
- Lân cận: 10 học khu gần nhất theo tọa độ văn phòng, cộng tối đa 10 học khu cùng quận; khoảng cách
  là km đường tròn lớn.
- Nạp D1 (`import-districts.yml`): upsert theo mã NCES, dòng không đổi thì không ghi; học khu không còn
  trong tệp chuyển `active = 0`, không xóa; lân cận thay toàn bộ. Production chỉ nạp từ commit đã có
  trên `main`. Báo cáo lưu ở Release `report-districts-*` và `docs/reports/districts-ccd-2024-25.md`.
