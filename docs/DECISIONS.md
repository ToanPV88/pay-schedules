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

## D-016: Importer bảng lương của bang (Công đoạn 4): định dạng và công cụ đọc

- Ngày: 2026-11-12. Claude quyết.
- Nguồn (Release `src-state-salaries-2425-20261112-43205697035`, kê khai ở
  `pipeline/sources/state-salaries-2425.json`):
  - California J-90 2024-25 và 2023-24: https://www3.cde.ca.gov/ds-downloads/fd/cs/j902425.exe,
    `j902324.exe`, kèm readme. Tệp `.exe` là ZIP tự giải nén: mở bằng `zipfile`, **không chạy**. Bên
    trong là CSDL Access (`tsalYYZZ.accdb`), đọc bằng `mdb-export` của **mdbtools** (gói apt, cài trong
    workflow). Bảng dùng: `TSAL1ZZ` (học khu), `TSAL2ZZ` (tên cột), `TSAL3ZZ` (lương theo cột × bậc).
  - Kentucky: workbook "Certified Salary Schedule (2014-2026)" của KDE, mỗi năm tài chính một sheet,
    đọc bằng **openpyxl** (phụ thuộc runtime mới của pipeline).
- Phần đọc file tách khỏi phần dựng bảng (`read_j90` / `j90_schedules`): từ 2025-26 California chuyển
  sang C-90, chỉ cần thay phần đọc.
- Năm học: CA lấy từ tên bảng Access (`tsal325` = 2024-25); KY lấy từ cột Fiscal Year của sheet
  ("2025 - 2026" = 2025-26). Nhập mọi tệp J-90 có trong Release (hiện 2023-24, 2024-25) và 2 năm mới
  nhất của KY (2024-25, 2025-26), để có năm trước cho kiểm tra lương khởi điểm.
- Map mã học khu của bang sang NCES qua cột `ST_LEAID` của danh mục CCD 2024-25: `CA-<CDS 7 số>`,
  `KY-<quận 3 số><học khu 3 số>000` (mã KDE là 3 số giữa). Khớp 100% ở cả hai bang.
- Nạp D1 bằng workflow `import-schedules.yml` (preview qua nhánh `run/import-schedules-preview`,
  production qua `run/import-schedules-production`, chỉ từ commit đã có trên `main`). SQL đi qua bảng
  tạm `_imp_*`, chạy lại không tạo bản ghi trùng; bản mới của cùng khóa (học khu, năm, loại, tiêu đề)
  từ tệp nguồn khác sẽ thay bản published cũ (cũ chuyển `superseded`).
- Migration 0003 thêm chỉ mục `cells(schedule_id)`: hai chỉ mục duy nhất của `cells` là chỉ mục một
  phần nên truy vấn "mọi ô của một bảng" phải quét cả bảng (đo trên bản sao: 30 giây → dưới 1 giây).

## D-017: Dữ liệu nào của bang được nhập, dữ liệu nào bỏ (Công đoạn 4)

- Ngày: 2026-11-12. Claude quyết.
- **Không đọc** (nguyên tắc 3 của PLAN: không thu thập lương cá nhân): lương superintendent
  (`TS1_Supt`), lương trung bình hiệu trưởng (`TS1_Prin*`, `TS1_DPrin*`), số FTE theo từng ô
  (`TS3_FTE`, `TS3_Salcost`), các bảng phúc lợi TSAL4-6. Tệp "Superintendent's Salaries" của KY không
  được kê khai tải.
- CA, một bảng J-90 cho mỗi học khu, tiêu đề rỗng:
  - lane = cột J-90 theo thứ tự số cột, nhãn ghép nguyên văn từ 5 trường tên cột; bậc = số bậc J-90,
    `years_experience` để trống (bậc 1 không chắc là 0 năm);
  - ô không có lương trong J-90 (cột bắt đầu hoặc dừng ở bậc khác) ghi trống kèm ghi chú;
  - `contract_days` = `TS1_RDays` (số ngày làm việc của giáo viên cũ); `notes` ghi ngày hiệu lực;
  - phụ cấp ngoài bảng (bằng thạc sĩ, tiến sĩ, giáo dục đặc biệt, song ngữ, CLAD/BCLAD, National Board,
    4 khoản "khác" có mô tả) vào `stipends`. Giá trị dưới 100 USD (vd. "14" cho "SLP yr 1-5") không rõ
    đơn vị nên giữ nguyên văn ở `amount_raw`, không quy ra tiền.
- **Học khu hành chính chung của California** (5 supervisory union trong CCD: Modesto City Schools,
  Santa Rosa City Schools, Petaluma City, Santa Cruz City, Arena Union/Point Arena): J-90 nộp theo
  đơn vị chung, giáo viên hai học khu thành viên dùng một hợp đồng. Bảng được ghi cho từng học khu
  thành viên (LEA_TYPE 2, cùng mã UNION), `notes` ghi rõ "Shared schedule of …". Học khu thành viên có
  J-90 riêng thì giữ bảng riêng.
- Học khu trong tệp của bang mà CCD xếp là charter độc lập (LEA_TYPE 7) nằm ngoài danh mục site (D-015)
  nên bị bỏ qua, có ghi lý do trong báo cáo (4-6 học khu CA mỗi năm).
- KY, một bảng cho mỗi học khu:
  - lane = Rank V, IV, III, II, I (thấp đến cao); chuẩn hóa III → BA, II → MA, I → MA+30, IV/V để trống;
  - bậc = số năm kinh nghiệm 0-40 (`years_experience` = số năm);
  - chỉ lấy cột x1 (mã hạng 11/21/31…) là bảng cơ bản. Cột x2, x3 là bảng tùy chọn, nghĩa khác nhau
    theo học khu (KDE: "Optional"), nên không nhập;
  - hạng toàn 0.00 là không áp dụng, bỏ lane; một ô 0.00 trong hạng có áp dụng thành ô trống có ghi chú;
  - workbook không có số ngày làm việc nên `contract_days` để trống.
- Chuẩn hóa lane chỉ nhận nhãn rõ nghĩa: BA, BA+N, MA, MA+N, PhD. Nhãn như "BA+45 OR MA",
  "BA+60+CRED", "BA NON-CRED" để `lane_normalized` trống, tránh so sánh sai.

## D-018: Bộ kiểm tra Validate và quy tắc publish (Công đoạn 4, dùng lại ở Công đoạn 5)

- Ngày: 2026-11-12. Claude quyết.
- Module `pay_pipeline.schedules.validate`, sáu kiểm tra của PLAN Công đoạn 5. Trượt bất kỳ kiểm tra nào
  thì bảng ghi `draft` và mỗi loại lỗi một dòng `review_queue`; qua hết thì `published`.
  1. Không giảm theo bậc trong một lane, không giảm sang lane kế tiếp ở cùng bậc. So các ô có số liền
     nhau, bỏ qua ô trống. Ô có ghi chú là ngoại lệ được chấp nhận.
  2. Đủ ô bậc × lane; ô trống phải có ghi chú; bảng phải có ít nhất một ô có tiền.
  3. Khoảng hợp lý theo `pay_basis`: năm 15.000-300.000 USD, tháng 1.250-30.000, ngày 75-1.500,
     giờ 10-250.
  4. Năm học đúng dạng, không quá năm học kế tiếp (năm học bắt đầu 1/7) và không cũ hơn bảng đang
     published. Riêng tệp của bang được coi là lịch sử chính thức: năm cũ hơn vẫn được nhập và
     published, vì khóa gồm cả năm học nên không thay bảng mới hơn.
  5. Trích hai lần: hàm `compare_extractions` so từng ô; không áp dụng cho tệp của bang (đọc tất định),
     dùng ở Công đoạn 5.
  6. Lương khởi điểm (bậc 1, lane thấp nhất có số) đổi quá 20% so với năm trước của cùng học khu.
     Năm trước lấy trong cùng lần nhập, hoặc từ bảng đang published trong D1.
- Lane giảm ở chỗ nối hai khối của một bảng J-90 (vd. khối "NON-CRED" rồi khối "CRED", hoặc khối SPED)
  là cấu trúc thật, nhưng vẫn chuyển xem tay: tự đoán khối dễ publish sai.
- Giữ tay: `pipeline/review-holds.json` liệt kê bảng (bang, mã học khu của bang, năm học) cần người xem,
  kèm lý do, vd. khi kiểm tra chéo thấy ô sai. Bảng đó thành `draft` với lý do `[cross_check]`, kể cả
  khi lần nạp trước đã publish. Bảng nào nay trượt kiểm tra cũng bị đưa về `draft` như vậy.
- `district_summary` tính lại sau mỗi lần nạp cho các học khu vừa đụng tới, từ bảng teacher published
  đầu tiên của năm: `start_ba_cents` = bậc 1 của lane chuẩn hóa BA, `ma_step10_cents` = vị trí bậc 10
  của lane MA (với KY là 9 năm kinh nghiệm), `max_salary_cents` = ô lớn nhất. Không có lane BA/MA rõ
  nghĩa thì để trống.

## D-019: Pipeline PDF (Công đoạn 5): kiến trúc, model, secret, điểm lưu

- Ngày: 2026-11-12. Claude quyết; chủ dự án duyệt ngân sách chạy thử.
- Chạy theo lô trong workflow `pdf-pipeline.yml` (chạy tay: target, limit, budget_usd, state). Hàng
  đợi lấy từ D1: học khu đang hoạt động, chưa có bảng lương nào, chưa xử lý hoặc đã đến hạn chạy
  lại, đông học sinh trước.
- **Discover**: dò website học khu trong danh mục NCES (không dùng API tìm kiếm trả phí ở bản đầu):
  trang chủ, các link về HR / employment / salary / bargaining (cùng site, sâu ≤ 2, tối đa 20 trang),
  `/sitemap.xml`. Link tới PDF/DOCX/XLSX hoặc host tài liệu quen (Finalsite, Thrillshare, edl.io...)
  thành ứng viên, chấm điểm theo chữ trong link. Tải tối đa 4 ứng viên tốt nhất.
- **Lịch sự**: robots.txt, User-Agent có liên hệ, 2 giây giữa hai request tới cùng host (PLAN cho
  phép ≥ 1 giây; D-014 dùng 5 giây cho tệp nguồn lớn). 16 luồng song song, một đồng hồ chung theo host
  cho mọi luồng (`acquisition/shared.py`).
- **Classify**: không dùng model. Đọc chữ (`pdftotext -layout`; XML của DOCX; ô của XLSX), chấm từng
  trang theo số lượng số tiền cỡ lương năm, chữ step/BA/MA/Rank/teacher, trừ điểm chữ
  classified/administrator. PDF gần như không có chữ là bản quét: gửi ảnh trang cho model.
- **Extract**: Claude qua Messages API, trả lời bắt buộc qua một tool có JSON schema cố định
  (`record_salary_schedule`), prompt có phiên bản (`p1`). Chỉ gửi các trang đã chọn (cắt bằng
  **pypdf**, tối đa 6 trang; bản quét 8 trang đầu). Hai lần trích độc lập bằng hai model khác nhau:
  `claude-sonnet-5-5` (bản chính) và `claude-haiku-5-5` (bản đối chiếu). Kết quả thô lưu nguyên văn ở
  `extraction_runs`, kèm chi phí (µUSD) tính theo bảng giá ngày 12/11/2026.
- **Validate**: bộ kiểm tra D-018, lần này bật cả so khớp hai lần trích và kiểm tra năm học không cũ
  hơn bảng đang published. Model nói tài liệu không phải bảng lương giáo viên thì học khu ghi
  `no_schedule`. Không đọc được năm học thì không lưu bảng, học khu chuyển `review`.
- Một bảng giáo viên mỗi học khu mỗi năm: tiêu đề in trên tài liệu chuyển vào `notes`, cột `title`
  để trống (khóa published của D-012 không trùng do tiêu đề khác nhau).
- **Lưu trữ**: tệp tải về và báo cáo lưu ở Release `docs-<target>-<ngày>-<run>`; `source_documents`
  ghi `district_id`, `release_tag`, `asset_name`.
- **Điểm lưu**: migration 0004 thêm `district_pipeline` (trạng thái, số lần thử, hạn chạy lại),
  `document_candidates`, `document_classifications`. Hạn chạy lại: không có website 180 ngày, không
  mở được 30, không thấy tài liệu / không phải bảng lương 90, lỗi 7, published 180, chờ xem tay thì
  không tự chạy lại. Tệp đã trích có sha256 không đổi thì bỏ qua (`unchanged`). Hết hạn giờ (45 phút)
  hay hết ngân sách thì học khu còn lại giữ nguyên trạng thái, lô sau làm tiếp.
- **Secret mới `ANTHROPIC_API_KEY`**: chủ dự án tạo trong Claude Console (workspace riêng, có giới
  hạn chi tiêu) và đặt trong GitHub Actions secrets. Chỉ nằm ở `env` của bước `pay-pipeline
  pdf-extract`; `test_repo_consistency.py` kiểm tra. Thiếu key thì workflow chỉ chạy Discover/Classify.
- Phụ thuộc mới: `pypdf` (cắt trang). Công cụ hệ thống: `poppler-utils` (pdftotext) cài trong CI và
  workflow.

## D-020: Bộ chuẩn đo độ chính xác của pipeline PDF

- Ngày: 2026-11-12. Claude quyết.
- `pipeline/gold/*.json`: mỗi tệp là một bảng lương nhập tay từ tài liệu của học khu (Release, URL,
  sha256, trang, năm học, lane, bậc, ô). Bảng đầu tiên lấy từ các tài liệu đã kiểm tra chéo ở Công
  đoạn 4, đọc bằng `pdftotext` và đối chiếu với dữ liệu của bang; phần còn lại lấy từ lô chạy thử.
- `pay-pipeline pdf-eval` (workflow `pdf-eval.yml`) chạy classify → extract → validate trên từng tài
  liệu, so bản trích chính với bộ chuẩn: lane và bậc khớp theo nhãn (trùng hẳn trước, rồi chứa nhau),
  không khớp nhãn thì theo vị trí khi cùng số lượng; chỉ tính ô có số trong bộ chuẩn, đúng đến cent.
- Nghiệm thu (PLAN): trên các bảng sẽ publish, ≥ 99% ô đúng; không bảng nào có ô sai (hoặc sai năm
  học) mà vẫn qua Validate.

## D-021: Trang xem tay nội bộ

- Ngày: 2026-11-12. Claude quyết.
- Worker riêng `apps/review` (`pay-schedules-review`, bản preview `pay-schedules-review-preview`),
  không chung code với `apps/web` để không đụng Công đoạn 6. Không lập chỉ mục, không cache.
- Bảo vệ bằng HTTP Basic; mật khẩu là secret `REVIEW_PASSWORD` (GitHub secret, workflow
  `deploy-review.yml` đặt bằng `wrangler secret put`). Thiếu secret thì trả 503. POST phải có
  Origin trùng site (chống CSRF).
- Chức năng: hàng chờ (lọc theo bang), xem lưới cạnh link tài liệu gốc (kèm số trang), tô ô mà bản
  trích đối chiếu khác, sửa ô (ghi `review_edits`, migration 0005), duyệt (publish, thay bảng
  published cũ cùng khóa, đóng `review_queue`, tính lại `district_summary`), loại (kèm lý do; học
  khu chạy lại sau 90 ngày).
