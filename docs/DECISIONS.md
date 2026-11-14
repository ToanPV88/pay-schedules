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

- Ngày: 2026-11-12. Claude quyết.
- **Đã thay một phần bởi D-022**: bước Extract không gọi Claude, không có secret
  `ANTHROPIC_API_KEY`, không dùng pypdf. Các phần khác (Discover, Classify, điểm lưu, lưu trữ) giữ
  nguyên.
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

## D-022: Đọc bảng lương tất định, không dùng API AI

- Ngày: 2026-11-12. Chủ dự án quyết: không dùng API key (không gọi model trả phí).
- `pdf_pipeline/read.py` đọc bảng từ lớp chữ của tài liệu theo vị trí, như travienphi (ADR-0002 của
  travienphi cũng cấm API AI trả phí):
  - hàng dữ liệu = nhãn bậc (`1`, `31+`, `Step 4`, `0-3 Years`) + các số tiền cỡ lương năm; hàng chỉ
    có số ngay dưới thì nối vào (bảng in hai dòng mỗi bậc);
  - cột = gom mép phải các số tiền (số căn phải); mỗi số vào cột gần nhất, nên ô trống của bảng bậc
    thang vẫn trống; hai số rơi vào một cột thì coi như không hiểu bố cục;
  - nhãn lane = chữ tiêu đề ngay trên hàng đầu, đặt vào cột gần nhất; tiêu đề bảng chặn lại;
  - chọn bảng lớn nhất có chữ "teacher/certificated" gần đó và không có chữ classified/administrator.
- **Hai lần đọc độc lập** (thay cho hai model): pdfplumber (tọa độ chữ) và `pdftotext -layout`
  (cột ký tự). `compare_extractions` so số lane, nhãn bậc và từng ô; lệch thì chờ xem tay. Excel và
  bảng Word có ô rõ ràng nên đọc một lần.
- Không đọc được: PDF dạng ảnh quét (cần OCR, chưa làm), bảng không có nhãn bậc ở đầu hàng, bảng
  nằm trong trang HTML. Những học khu này ghi `no_schedule` với lý do, để xem tay hoặc làm sau.
- Kiểm tra lane: lane in từ cao xuống thấp (Rank I trước, cột Doctorate trước) được chấp nhận khi đó
  rõ ràng là chiều của bảng (≥ 3 cặp giảm và gấp ≥ 3 lần số cặp tăng); mọi cặp phải theo cùng chiều.
- Chi phí đọc: 0 USD. Phụ thuộc: `pdfplumber` thay `pypdf`.
- Bộ chuẩn (D-020) đo trên bộ đọc này. Bộ chuẩn ban đầu dựng bằng `pdftotext` nên chưa độc lập
  hoàn toàn với bộ đọc; các bảng thêm sau được đối chiếu bằng mắt trên ảnh trang.
- Kiểm tra thêm cho bảng đọc từ website (ngoài Validate chung, `pdf_checks` trong `run.py`, dùng
  chung với bộ chuẩn), thêm sau chạy thử ngày 2026-11-12:
  - `schedule_scope`: bảng chỉ cho một nhóm giáo viên (thuê trước một ngày, ngoài lớp học) xếp sau
    bảng chung; nếu chỉ có nó thì chờ xem tay;
  - `lane_label`: nhãn lane lẫn chữ của đoạn văn bên cạnh bảng thì chờ xem tay;
  - `school_year`: bảng cũ hơn hai năm học so với năm học hiện tại thì chờ xem tay.
- Bộ đọc có số phiên bản (`layout-text@N`, `pdfplumber-words@N`...). Tài liệu chỉ được coi là đã xử lý
  (bỏ qua khi sha256 không đổi) nếu đã đọc bằng phiên bản hiện tại; đổi cách đọc thì tăng số.

## D-023: Xóa cache website sau khi publish: hàng chờ trong D1, Worker xem tay gửi đi

- Ngày: 2026-11-12. Claude quyết (nối D-102: "Pipeline gọi endpoint này sau bước Publish").
- Bối cảnh: Worker web cache trang theo thẻ và mở `POST /internal/purge` (Bearer `PURGE_TOKEN`).
  Pipeline chạy trên GitHub Actions nạp D1 bằng `wrangler d1 execute`; nếu gọi thẳng endpoint thì
  workflow phải biết URL của Worker web và cầm thêm một secret ngay cạnh bước nạp.
- Nội dung:
  - Migration 0006: bảng `cache_purge_queue (district_id PK, queued_at, attempts, last_error)`.
  - SQL nạp bảng lương (`schedules/d1sql.py`, dùng cho cả nhập từ bang và pipeline PDF) ghi mọi học
    khu được chạm vào hàng chờ, trong cùng tệp SQL với dữ liệu. Nút "Duyệt" của trang xem tay cũng
    ghi vào, rồi gửi ngay một lô.
  - Worker xem tay (`apps/review`) có service binding `WEB` tới Worker web và cron mỗi 10 phút: lấy
    tối đa 10 lô × 100 học khu (giới hạn của endpoint), gọi `/internal/purge`; thành công thì xóa dòng
    (chỉ khi `queued_at` chưa đổi), lỗi thì tăng `attempts`, ghi `last_error`, dừng và thử lại lần
    sau; quá 20 lần thì nằm lại, trang hàng chờ hiện số dòng và lỗi gần nhất.
  - Secret mới **`PURGE_TOKEN`** (GitHub secret, chủ dự án tạo, một chuỗi ngẫu nhiên). `deploy.yml`
    đặt nó cho Worker web production, `deploy-review.yml` đặt cho Worker xem tay production, mỗi chỗ
    ở một bước `wrangler secret put PURGE_TOKEN` riêng. Workflow pipeline không cầm secret này.
  - Bản preview không xóa cache: Worker web preview chạy theo alias của từng PR, mỗi alias có cache
    riêng; Worker xem tay preview không có binding `WEB` và không có cron.
- Hệ quả: trang web cập nhật trong vòng ~10 phút sau khi nạp hoặc duyệt. Thiếu `PURGE_TOKEN` thì
  không có lỗi, chỉ là cache hết hạn theo `s-maxage` (1 ngày).

## D-100: URL, lập chỉ mục và thứ tự trang của web (Công đoạn 6)

- Ngày: 2026-11-12. Claude quyết.
- URL:
  - `/` trang chủ; `/<bang>` danh sách học khu của bang; `/<bang>/<học-khu>` bảng mới nhất;
    `/<bang>/<học-khu>/<YYYY-YY>` năm cũ. URL năm bằng năm mới nhất chuyển 301 về URL không có năm;
    năm không có hoặc sai dạng trả 404.
  - `/search`, `/compare`, `/calculator`, `/about`, `/methodology`, `/privacy`, `/terms`, `/contact`,
    `/report` (D-104), `/demo` (D-101), `/sitemap.xml`, `/robots.txt`, `/healthz`.
- Lập chỉ mục:
  - Khi `INDEXABLE` khác `"true"` (hiện tại, theo D-002): mọi phản hồi có `X-Robots-Tag: noindex,
    nofollow`, thẻ meta cùng nội dung, `robots.txt` chặn tất cả.
  - Khi mở: trang học khu chỉ index khi có bảng published và có học khu lân cận; học khu chưa có bảng
    published hiện "Schedule not found" và noindex. Trang có query string (sắp xếp, máy tính, phân
    trang), `/search` và `/report` luôn noindex.
  - Sitemap chỉ gồm trang học khu có bảng teacher published (URL chính và URL của năm cũ), tối đa
    50.000 URL. Trang bang và trang công cụ không vào sitemap.
- Trang học khu theo thứ tự của PLAN: tiêu đề → tóm tắt (BA bậc 1, MA bậc 10, tối đa) → bảng lương
  và máy tính → so sánh với học khu lân cận → phụ cấp và ghi chú → nguồn (link tài liệu, trang/sheet,
  ngày tải) → các năm khác.
- Trang bang: 200 học khu mỗi trang; sắp xếp theo tên, lương khởi điểm, MA bậc 10, tối đa làm ở server
  (link ở tiêu đề cột). JavaScript chỉ sắp tại chỗ khi mọi dòng nằm trên một trang.

## D-101: Render ở server, JavaScript chỉ để tăng cường; trang /demo chỉ ở bản xem trước

- Ngày: 2026-11-12. Claude quyết.
- Mọi bảng lương nằm trong HTML server gửi (`<table>` có `<th scope>`), đọc được khi tắt JavaScript
  (có test). Máy tính là form GET: server tính và trả kết quả; `site.js` (không thư viện, không tải
  từ nơi khác) chỉ cập nhật tại chỗ để khỏi tải lại trang.
- Máy tính chỉ đọc đúng ô của bảng, không nội suy; ô trống hiện ghi chú, không có số.
- `/demo` render một bảng GIẢ LẬP (AGENTS.md §2.6) để xem giao diện và đo Lighthouse khi CSDL chưa có
  dữ liệu. Chỉ có khi `ENVIRONMENT` khác `production`; production trả 404. Trang có dòng ghi rõ là dữ
  liệu bịa và luôn noindex.

## D-102: Cache ở edge bằng Workers Cache, xóa theo thẻ khi publish (bổ sung D-007)

- Ngày: 2026-11-12. Claude quyết.
- Bối cảnh: D-007 ghi rằng Cache API của Workers không chạy trên `*.workers.dev`, nên dời cache sang khi
  có tên miền. Cloudflare nay có **Workers Cache** (bật bằng `"cache": { "enabled": true }` trong
  `wrangler.jsonc`), chạy cả trên `workers.dev`, mỗi phiên bản xem trước có cache riêng, không tính
  phí riêng (mọi request vẫn tính theo giá request của Workers). Đã kiểm trên tài liệu Cloudflare
  ngày 2026-11-12.
- Nội dung:
  - Trang trả `Cache-Control: public, max-age=300, s-maxage=86400, stale-while-revalidate=3600`; trang
    nội dung tĩnh lâu hơn; `/healthz`, `/report`, `/internal/*` là `no-store`.
  - Header `Cache-Tag`: `pages` cho mọi trang, `district-<id>`, `state-<mã bang>`, `home`, `sitemap`,
    `compare`.
  - `POST /internal/purge` với `Authorization: Bearer <PURGE_TOKEN>` và `{"districtIds": [...]}`
    (1-100 id): xóa thẻ của các học khu đó, học khu lân cận trỏ tới chúng, bang của chúng, cùng
    `home`, `sitemap`, `compare`. Không đặt `PURGE_TOKEN` thì luôn trả 401. Môi trường không có
    `ctx.cache` (test cục bộ) trả 501 kèm danh sách thẻ.
  - Pipeline (Công đoạn 5) gọi endpoint này sau bước Publish. Phần đó thuộc phiên làm pipeline.
- Phần của D-007 về cache được thay bằng mục này; phần còn lại của D-007 giữ nguyên.

## D-103: Khung quảng cáo giữ chỗ, chưa gắn mã

- Ngày: 2026-11-12. Claude quyết.
- Biến `AD_SLOTS`: `"true"` thì render `<aside class="ad-slot">` ở ba vị trí của trang học khu (dưới
  tóm tắt, trước so sánh lân cận, cuối trang); các trang khác chưa có. Khung có chiều cao cố
  định (280 px trên mobile, 250 px từ 48rem) để quảng cáo về sau không làm xô bố cục (CLS).
- Production để `"false"` cho tới khi có mã quảng cáo (Công đoạn 9); bản xem trước để `"true"` để
  Lighthouse đo cả khung.

## D-104: Form báo lỗi, Turnstile tắt mặc định, không lưu dữ liệu cá nhân

- Ngày: 2026-11-12. Claude quyết.
- Migration `0010_error_reports.sql`: bảng `error_reports` (học khu, bảng lương nếu có, đường dẫn trang,
  nội dung 10-2000 ký tự, thời điểm, trạng thái xử lý). **Không lưu** IP, email, tên hay user agent.
- Form chỉ bật khi đặt đủ `TURNSTILE_SITE_KEY` (biến) và `TURNSTILE_SECRET_KEY` (secret). Thiếu một trong
  hai thì không có nút "Report an error" và `/report` trả 404.
- Kiểm tra theo thứ tự: trường bẫy `website` (bị điền thì báo đã nhận nhưng không lưu) → độ dài → bảng
  lương phải là bảng published của đúng học khu → Turnstile Siteverify (gửi `CF-Connecting-IP` cho
  Cloudflare, không lưu) → ghi D1.
- Việc của chủ dự án để bật: tạo widget Turnstile cho tên miền của Worker; đặt `TURNSTILE_SITE_KEY` trong
  `vars` của `wrangler.jsonc`; `npx wrangler secret put TURNSTILE_SECRET_KEY` (thêm `--env preview` cho
  bản xem trước).

## D-105: Tên hiển thị của học khu

- Ngày: 2026-11-12. Claude quyết (D-015 để Công đoạn 6 quyết cách hiển thị).
- D1 giữ tên nguyên văn của NCES. Khi hiển thị: tên, thành phố, quận viết hoa toàn bộ thì đổi sang
  Title Case; giữ nguyên chữ viết tắt quen thuộc (ISD, CISD, USD, UFSD, CSD, SD, ESD, HSD, UHSD, CUSD,
  JUSD, UESD, RSU, SAU, SAD, MSAD, PSD, RE, DC), từ có chữ số và số La Mã; từ nối (of, the, and…) viết
  thường. Tên đã có chữ thường giữ nguyên ("DeSoto Cons SD 86").
- Hàm `displayName` ở `packages/db/src/names.ts`, áp trong các truy vấn của `site.ts`.

## D-106: Đo Lighthouse mobile trong CI

- Ngày: 2026-11-12. Claude quyết.
- Job `lighthouse` của `deploy.yml` chạy sau job `preview` của PR: `lighthouse@13.6.0` (cần Node ≥ 22.19),
  cấu hình mobile mặc định, đo `/`, `/demo` và trang học khu đầu tiên trong sitemap, mỗi trang 3 lần
  lấy trung vị. Thất bại khi Performance, Accessibility hoặc Best practices dưới 90. SEO ghi vào tóm
  tắt nhưng không tính vì site đang noindex có chủ đích (D-002).
- Job không checkout mã, không dùng secret, quyền chỉ đọc.

## D-024: Kiểm tra `monotonic_lane` so lane theo trình độ ghi trên nhãn; bỏ qua chênh do làm tròn

- Ngày: 2026-11-13. Claude đề xuất, chủ dự án đồng ý.
- Bối cảnh: sau lần nhập tệp của bang (Công đoạn 4), 202 bảng CA/KY nằm trong hàng chờ xem tay, phần
  lớn vì `monotonic_lane`. Tệp J-90 của California in nhiều ngạch cạnh nhau trong một bảng: lane giáo
  viên chưa có chứng chỉ (NON-CRED, INTERN, EMERG), lane SPED, lane theo số ngày làm việc, lane "+MA"
  xen giữa các lane đơn vị học. Lane cuối của ngạch NON-CRED trả cao hơn lane đầu của ngạch có chứng
  chỉ là đúng với nguồn, không phải lỗi đọc. Tệp của Kentucky trả lương lẻ xu nên có chênh vài xu
  đến vài đô ($91,493.01 rồi $91,493.00).
- Nội dung (`pipeline/src/pay_pipeline/schedules/validate.py`):
  - Đọc nhãn lane thành bậc học (`<BA`, BA, MA, 2MA, PhD), số đơn vị (`BA+30`, `MA+60+17`) và **ngạch**
    (phần còn lại của nhãn: `NON-CRED`, `SPED`, `195 DAYS`…). `CRED`, `PRELIM`, `FULL STEP`, `WHOLE YR`
    không tạo ngạch riêng. Với "A OR B" chỉ đọc vế đầu.
  - Khi ít nhất 75% nhãn đọc được: chỉ so hai lane **cùng ngạch** mà lane này có bậc học và số đơn vị
    đều không thấp hơn lane kia (và cao hơn ở ít nhất một). Số đơn vị chỉ so khi hai nhãn bắt đầu
    bằng cùng bậc học (`MA+30` tính từ MA, `BA+75+MA` tính từ BA); `BA<45` không có số đơn vị để so.
    Hai lane không so được (`BA+30+MA` và `BA+45`) thì bỏ qua. Thứ tự in trong tài liệu không còn
    quan trọng.
  - Khi nhãn không đọc được (Rank I–V, Column 1, Class A…): giữ cách cũ, so theo thứ tự in.
  - Lương giảm không quá $10 (giữa hai bậc hoặc hai lane) coi là làm tròn của nguồn, không báo.
- Kết quả đo trên tệp nguồn thật (CA J-90 2023-24, 2024-25; KY 2024-25, 2025-26): số bảng trượt
  `monotonic_step`/`monotonic_lane` giảm từ 195 xuống 90; không bảng nào đang qua lại thành trượt
  (`docs/reports/validate-lane-rank-2026-11-13.md`). Phần còn lại là chỗ lạ thật của nguồn (lương
  giảm khi tăng bậc, lane trình độ cao trả thấp hơn) và vẫn cần người xem. Bộ chuẩn PDF: Chatom
  2024-25 chuyển từ xem tay sang publish (125/125 ô đúng); vẫn 0 bảng sai lọt Validate.
- Nhập lại tệp của bang (`d1sql.py`) tôn trọng quyết định của người xem tay: bảng đã **duyệt** không
  bị đưa về draft, bảng đã **loại** không bị publish và không nhận lý do mới. Lý do xem tay đang mở
  mà kiểm tra không còn báo thì được đóng với `resolution = "auto: the checks no longer report this on
  re-import"`.

## D-025: Workflow Deploy chỉ chạy khi thay đổi chạm tới web hoặc CSDL

- Ngày: 2026-11-13. Chủ dự án yêu cầu tiết kiệm phút GitHub Actions (repo riêng tư).
- `deploy.yml` (bản xem trước, Lighthouse, deploy production) chỉ chạy khi PR hoặc commit trên main
  sửa `apps/web/**`, `packages/db/**`, `package.json`, `package-lock.json` hoặc chính `deploy.yml`.
  PR chỉ sửa pipeline hay tài liệu chỉ chạy CI (khoảng 2 phút thay vì 6).
- Migration nằm trong `packages/db/**` nên vẫn được áp lên preview và production như trước.
- Quy ước làm việc: trước mỗi việc tốn phút Actions (đẩy commit lên PR, chạy pipeline, nhập dữ liệu,
  chạy lại workflow), Claude báo ước tính số phút và chờ chủ dự án đồng ý.

## D-026: Bộ đọc PDF @5: gom dòng theo chiều cao chữ, bậc đặt tên bằng chữ cái, chọn bảng năm học chuẩn

- Ngày: 2026-11-13. Claude quyết, sau khi đo trên 38 tài liệu của lô production đầu
  (`docs-production-20261112-43271718628`) và bộ chuẩn 30 bảng, tại máy (không tốn phút Actions).
- Bộ đọc lên phiên bản 5 (`pdfplumber-words@5`, `layout-text@5`, `xlsx-cells@5`, `docx-cells@5`):
  tài liệu đã đọc bằng @4 sẽ được đọc lại ở lô sau.
  - pdfplumber: chữ của một hàng có thể lệch vài điểm theo chiều dọc (nhãn bậc đặt thấp hơn số tiền,
    Mobile County). Chữ bắt đầu trong khoảng 40% chiều cao của chữ đầu dòng thì thuộc cùng dòng
    (trước: cố định 2,5 điểm).
  - Bậc đặt tên bằng chữ cái (`C`…`Z`, `AA`, `T&U`; Florida, Maryland) là nhãn bậc; thứ tự chữ cái
    dùng như thứ tự số. Bậc chữ cái không có số năm kinh nghiệm.
  - Khi bảng đầu tiên ghi lịch làm việc ngoài năm học chuẩn của giáo viên (175–200 ngày, ví dụ
    240/260 ngày) và một bảng sau ghi năm học chuẩn, chọn bảng sau.
  - Chỉ bộ đọc thứ hai thấy bảng: dùng lần đọc đó và chuyển xem tay (`double_extraction`) thay vì bỏ
    học khu là "không có bảng".
- Kiểm tra mới:
  - `flat_schedule` (chỉ cho bảng đọc từ website): mọi ô cùng một số tiền từ 3 bậc trở lên, chờ xem
    tay (đúng với một số nguồn như bảng thưởng hiệu suất của Volusia, nhưng cũng giống cột đọc sai).
  - `lane_label`: nhãn lane chỉ còn một chữ chung (`RANK`, `CLASS`, `LANE`, `COLUMN`…), tức tên lane
    đã mất khi đọc.
- Kết quả: bộ chuẩn không đổi (24 publish, 6 xem tay, 2560/2560 ô đúng, 0 bảng sai lọt Validate). Trên
  38 tài liệu của lô production: 3 học khu chuyển từ "không có bảng" sang chờ xem tay (Mobile County,
  Collier, Volusia); không học khu nào đổi kết quả khác.
- Chưa làm (cần cách đọc riêng, ít học khu): bảng xoay ngang (lane theo hàng, bậc theo cột: Knox),
  mỗi bậc nhiều dòng thành phần (Seattle), nhiều bảng nhỏ đặt cạnh nhau lặp nhãn bậc (Frederick,
  Hawaii có mã ô trước mỗi số), sổ lương Excel theo tháng (Wake).

## D-027: Discover: đọc sitemap trước, trang lương sâu thêm một tầng, mở trang thư mục tài liệu

- Ngày: 2026-11-13. Claude quyết.
- Bối cảnh: ở lô production đầu, 21/100 học khu không thấy link tài liệu (`no_candidates`) và nhiều học
  khu chỉ tải được tài liệu không phải bảng giáo viên. Nhiều website để bảng lương ở tầng 3–4
  (Trang chủ → Phòng ban → Nhân sự → Lương) hoặc trong trang "thư mục tài liệu" của Thrillshare.
- Nội dung (`pipeline/src/pay_pipeline/discover/crawl.py`, `pdf_pipeline/gather.py`):
  - Sau trang chủ, đọc `/sitemap.xml` (nếu là sitemap index thì đọc tiếp tối đa 3 tệp con, ưu tiên
    tệp trang). Tài liệu trong sitemap là ứng viên; tối đa 10 trang có địa chỉ giống trang lương
    (`salary`, `compensation`, `negotiated agreement`…) được đưa lên đầu hàng crawl.
  - Link có chữ lương hoặc thỏa ước được theo thêm một tầng (tầng 3); ngân sách trang 20 → 25.
  - Ứng viên dẫn tới trang thư mục tài liệu (không có tệp, chỉ có link tới các trang tài liệu
    con): mở tối đa 2 trang con giống bảng lương nhất, ngoài 4 tài liệu mỗi học khu.
  - Vẫn tôn trọng robots.txt (ParentSquare, Google Drive chặn: không vượt).
- Đo trên preview (37 học khu đang `no_candidates`, Release `docs-preview-20261113-43356207992`):
  8 học khu tìm được tài liệu, 4 đọc được bảng (Dallas, Cherry Creek, Clayton County, Boston:
  2 publish, 2 chờ xem tay); 27 vẫn không thấy link.

## D-028: Bảng từ tệp của bang publish "như nguồn"; không trỏ người xem tới tệp .exe

- Ngày: 2026-11-13. Claude đề xuất, chủ dự án đồng ý (không đủ thời gian duyệt tay ~90 bảng).
- Bảng lấy từ tệp dữ liệu của bang (CA J-90, KY) là số học khu tự khai với bang, không có bước đọc
  có thể sai. Khi kiểm tra chỉ thấy số lạ của chính nguồn (`monotonic_step`, `monotonic_lane`,
  `start_change`), bảng vẫn publish. Kết quả kiểm tra được giữ trong `review_queue` dưới dạng dòng đã
  đóng với `resolution` bắt đầu bằng `as reported` (`schedules/state_import.py`, `d1sql.py`).
- Trang học khu ghi ở mục Source: "Shown as the district reported it to the state" và kiểm tra nào đã
  báo; trang Methodology giải thích. Không sửa số liệu đã khai.
- Vẫn chờ xem tay: giữ lại từ kiểm tra chéo (`cross_check`, `review-holds.json`), lỗi cấu trúc
  (`cell_count`, `range`, `school_year`...), và mọi bảng đọc từ PDF.
- Nguồn J-90 là tệp ZIP tự giải nén `.exe` của CDE (pipeline chỉ mở như ZIP, không chạy). Trang web
  không link thẳng tới tệp đó mà tới trang dữ liệu chính thức https://www.cde.ca.gov/ds/fd/cs/, ghi
  tên tệp; CSDL vẫn giữ URL tệp và sha256. Tệp `.exe` khác (nếu có) chỉ ghi tên máy chủ, không link.

## D-029: Oklahoma: nhập sổ "Local Salary Schedules" của Sở Giáo dục bang

- Ngày: 2026-11-13. Chủ dự án đồng ý.
- Nguồn: OSDE, Office of School Personnel Records, "Oklahoma Public Schools Local Salary Schedules"
  2025-26 và 2024-25 (PDF, ~380 trang). Học khu phải nộp bảng lương cho bang; mỗi học khu có bảng
  riêng được in một trang theo cùng mẫu 18 cột (cử nhân, cử nhân + giờ ×3, các cột đó có chứng chỉ
  National Board, thạc sĩ…, tiến sĩ). Học khu trả theo bảng tối thiểu của bang chỉ được liệt kê tên;
  học khu đó nhận bảng tối thiểu in trong sổ, kèm ghi chú.
- Đọc (`pipeline/src/pay_pipeline/schedules/ok_sde.py`, importer `ok_sde@1`): `pdftotext -layout`,
  cột lấy theo vị trí 18 chữ tiêu đề, số tiền vào cột gần nhất. Trang không đúng 18 cột, hoặc số
  tiền lệch quá 40% khoảng cách cột, bị bỏ (không đoán). Cột trống ("0 Hrs") không thành lane. Mã
  học khu `72 - I001` ↔ NCES `ST_LEAID` `OK-72-I001`.
- Đo tại máy: 2025-26 có 369 trang học khu + 128 học khu theo bảng tối thiểu; ghép được 506/507 học
  khu thường của Oklahoma. Độ lệch lớn nhất của số tiền so với tâm cột: 0,25 khoảng cách cột.
- Kiểm tra lane theo trình độ (D-024) đọc thêm cách viết đầy đủ: `Bach.`/`Bachelor's` = BA,
  `Mast.` = MA, `Doct.`/`Doctor's` = PhD, `+ 15 Hrs` = +15, `NBCT`/`National Board Certification`
  là một ngạch riêng. Kết quả trên CA/KY và bộ chuẩn PDF không đổi.
- Số lạ của chính nguồn (vd. Yukon 2024-25: NBCT Bach. bậc 22 là 94,966 giữa 64,320 và 65,611) được
  publish như nguồn theo D-028, trang web ghi rõ.

## D-030: Pipeline PDF chạy song song theo lô

- Ngày: 2026-11-13. Chủ dự án đồng ý (chạy toàn quốc trong lúc repo để public, Actions miễn phí).
- `pdf-pipeline.yml` tách thành `plan` → `run` (matrix, tối đa 20 lô, giới hạn đồng thời của gói
  Free) → `archive` → `load`. `plan` đọc hàng đợi D1 một lần; `pdf-shard` chia theo host website
  (bỏ `www.`): mọi học khu cùng một host ở cùng một lô, nên throttle theo host trong một job vẫn
  phủ mọi request tới host đó, không có hai job cùng gõ một site.
- Mỗi lô một Release `<tag>-s<i>` và `run_key` riêng. `load` nạp SQL từng lô lần lượt; lô lỗi
  không chặn lô khác. Học khu chưa kịp bắt đầu trước hạn (`deadline_minutes`, tối đa 270) giữ
  nguyên trạng thái hàng đợi cho lần sau, như trước.
- Tham số trong `pipeline/pdf-pipeline-run.json`: thêm `shards` (mặc định 1) và
  `deadline_minutes` (mặc định 45). `limit` cho phép tới 5 chữ số.

## D-031: Hawaii: bảng lương giáo viên toàn bang của HIDOE

- Ngày: 2026-11-13. Chủ dự án đồng ý.
- Hawaii chỉ có một học khu (Hawaii Department of Education, NCES 1500030, `ST_LEAID` `HI-001`),
  nên bảng của bang chính là bảng của học khu, không phải mức tối thiểu được cộng thêm phụ cấp địa
  phương. Bang có bảng chung nhưng học khu trả thêm (North Carolina, Georgia...) thì không làm theo
  cách này: số trên site sẽ thấp hơn lương thật.
- Nguồn: "Teacher's Annual Rate Salary Schedule (10-Month)" (Exhibit E, hợp đồng HSTA), PDF một
  trang trên hawaiipublicschools.org. Bảng 12 tháng không nhập.
- Đọc (`hi_doe.py`, importer `hi_doe@1`): theo mã lương in cạnh mỗi số (`T03-14A` = Class III, bậc
  14A), không theo vị trí cột; số bậc ở lề có dấu chú thích dính liền (`95` = bậc 9, chú thích 5).
  Thiếu ô hoặc trùng mã thì bỏ cả bảng.
- Bậc đầu là bậc 4, nguồn ghi "(ENTRY LEVEL)". Kiểm tra `step_start` bỏ qua hàng đầu có nhãn
  "entry level", vì nguồn đã nói đó là hàng đầu.

## D-032: Pipeline PDF chạy hằng tuần theo hạn của từng học khu

- Ngày: 2026-11-13. Chủ dự án đồng ý.
- Học khu đổi bảng lương mỗi năm nhưng không cùng lúc (đa số duyệt tháng 4-8, nhiều nơi muộn vì
  đàm phán công đoàn), nên không chạy một đợt lớn mỗi năm. `pdf-pipeline.yml` có thêm `schedule`
  (thứ Bảy 19:17 UTC, sáng Chủ nhật giờ Việt Nam), luôn vào production, chỉ lấy học khu đã đến
  hạn theo `RETRY_DAYS` (published 180 ngày, unchanged 120, no_candidates/no_schedule 90...).
- Tham số trong `pipeline/pdf-pipeline-weekly.json`: tối đa 600 học khu, 4 lô, hạn 60 phút. Ước
  khoảng 130 phút mỗi tuần, khoảng 550 phút mỗi tháng: trong 2.000 phút miễn phí của repo private.
  Học khu đến hạn nhiều hơn 600 thì để tuần sau (hàng đợi xếp theo số học sinh).
- Tháng 8-10, mùa ra bảng mới, có thể chạy thêm lượt lớn bằng nhánh `run/pdf-pipeline-production`.
- Hàng đợi đổi: trước đây bỏ mọi học khu đã có bảng, nên bảng năm mới không bao giờ được lấy. Nay
  học khu đã đến `next_run_at` vào hàng đợi cả khi đã có bảng published. Tài liệu không đổi thì
  bỏ qua nhờ `known.json` (url + sha256); bảng cùng năm thành bản draft song song (D-012); bảng cũ
  hơn bản published bị Validate giữ lại. Học khu đang có draft chờ duyệt vẫn không vào.

## D-033: Release của pipeline PDF gói tài liệu thành docs.tar

- Ngày: 2026-11-13. Lượt toàn quốc đầu tiên (run 43379595661) có khoảng 6.000 tài liệu; job
  `archive` tải từng tệp lên Release và bị GitHub chặn ("API rate limit exceeded for installation")
  sau khoảng 2.300 tệp, nên `load` không chạy.
- Từ nay mỗi lô có một `docs.tar` chứa mọi tài liệu học khu, cộng các tệp báo cáo tải riêng
  (`manifest.json`, `report.md`, `work.json`, `extractions.json`). `asset_name` trong D1 là tên tệp
  bên trong `docs.tar`; Release cũ (trước D-033) vẫn có từng tệp riêng.
- Logic nằm trong `scripts/archive-releases.sh`, chạy lại được: Release đã có thì chỉ tải phần còn
  thiếu (một Release đã có đủ từng tệp thì không thêm docs.tar).
- `pdf-pipeline-resume.yml` lưu Release và nạp D1 lại cho một lượt đã xong bước `run`, từ artifact
  của lượt đó (giữ 7 ngày); tham số trong `pipeline/pdf-pipeline-resume.json`.

## D-034: Tự phân loại hàng chờ xem tay

- Ngày: 2026-11-13. Chủ dự án đồng ý. Sau lượt toàn quốc, hàng chờ có 232 bảng; chủ dự án không
  duyệt tay hết được.
- Worker xem tay (`apps/review`) chạy `autoTriage` mỗi lần cron (10 phút), tối đa 50 bảng mỗi lần.
  Chỉ xét bảng draft mà mọi lý do còn mở đều thuộc nhóm an toàn:
  - `[step_start]` (bảng bắt đầu ở bậc cao), khi không kèm `[double_extraction]`: hai bộ đọc cùng
    thấy bảng bắt đầu ở đó, nên đó là cách nguồn in. Publish như nguồn.
  - `[school_year] Bảng năm ... đã cũ` của pipeline PDF: năm học bắt đầu trong 3 năm trước năm học
    hiện tại thì publish như nguồn (trang web ghi năm và nói có thể có bảng mới hơn); cũ hơn thì
    loại, học khu được tìm lại sau 90 ngày. Kiểm tra cùng mã "cũ hơn bảng đang published" không
    thuộc nhóm này.
- Publish dùng chung câu lệnh với nút "Duyệt"; resolution `as reported: auto-triage (D-034)`, nên
  trang web hiện mã kiểm tra như bảng publish như nguồn của D-028. Loại thì resolution bắt đầu bằng
  `rejected: auto-triage (D-034)`; lần nhập sau không mở lại (như loại tay).
- Học khu kẹt trạng thái `review` mà không có bảng draft (không đọc được năm học) được chuyển sang
  `no_schedule`, tìm lại sau 90 ngày, thay vì nằm im mãi.
- Câu trên trang web đổi thành "Shown as the source published it" vì giờ áp dụng cả cho bảng đọc từ
  website học khu, không chỉ tệp của bang.

## D-035: Suy website học khu từ website các trường

- Ngày: 2026-11-13. Chủ dự án đồng ý. Danh mục học khu NCES 2024-25 bỏ trống WEBSITE của 1.218 học
  khu thường; pipeline PDF không có chỗ bắt đầu nên các học khu này nằm ở `no_website`.
- Nguồn thêm: danh mục trường NCES CCD 2024-25 (`ccd_sch_029`), Release
  `src-nces-ccd-schools-2425-*` (manifest `pipeline/sources/nces-ccd-schools-2425.json`).
- Chỉ dùng khi tệp học khu bỏ trống. Host phổ biến nhất trong website các trường của học khu phải
  được ít nhất 2 trường và 60% số trường có ghi website cùng báo; học khu chỉ có một trường thì lấy
  website của trường đó. Không dùng host dùng chung (Facebook, Google, Blogspot, Wix, Weebly,
  Squarespace, WordPress.com, mạng xã hội) và host `.gov`.
- Trên tệp thật: suy được 301 website (NH 92, GA 49, IL 47, VT 33, WA 30, MI 27...), ví dụ
  Tacoma (70 trường cùng `tacoma.k12.wa.us`). Nebraska, Idaho, Louisiana, Rhode Island bỏ trống
  website ở cả tệp trường; cần danh bạ riêng của bang (chưa làm).

## D-037: Website học khu từ danh bạ của bang

- Ngày: 2026-11-13. Chủ dự án đồng ý. Bốn bang bỏ trống website ở cả danh mục học khu lẫn danh mục
  trường của NCES (Nebraska, Idaho, Louisiana, Rhode Island).
- `pipeline/sources/district-websites.csv` (`nces_id,website,source`): website lấy từ danh bạ do bang
  công bố, ghép với NCES theo tên, chỉ giữ trang chủ (scheme + host). Dùng khi tệp học khu NCES bỏ
  trống; đứng trước website suy từ trường (D-035).
- Louisiana: "District Directory 2017-2018" của LDOE (Release `src-state-directories-*`), 69/69 học
  khu ghép được. Danh bạ trường 2026-27 của LDOE không có cột website. Danh bạ cũ nên vài website có
  thể đã đổi; pipeline sẽ ghi `unreachable` cho những chỗ đó.
- Rhode Island, Idaho, Nebraska: danh bạ của bang chỉ có dạng trang tìm kiếm hoặc trang dựng bằng
  JavaScript; chưa làm.
## D-036: OCR cho bảng lương dạng ảnh quét

- Ngày: 2026-11-13. Chủ dự án đồng ý. 489 học khu chỉ có bảng lương dạng ảnh quét.
- Miễn phí và tất định (D-022): Poppler `pdftoppm` vẽ trang, Tesseract 5 đọc chữ kèm vị trí từng
  từ; các từ được ghép dòng rồi đưa vào chính bộ tìm bảng của PDF chữ (`read.find_tables`). Trước
  khi đọc, ảnh được đổi sang trắng đen, xóa đường kẻ bảng và nền tô (chỉ dùng Pillow, phụ thuộc có
  sẵn của pdfplumber). Sửa các lỗi OCR thường gặp ở số (S→$, O→0, l→1, dấu chấm hàng nghìn) và
  điền lại số bậc OCR làm rơi khi hai bậc kề nhau không để chỗ nghi ngờ.
- Tìm trang bằng một lượt nhanh ở 200 dpi, rồi đọc kỹ tối đa 2 trang với 6 cấu hình (300/400 dpi,
  psm 6/4, có/không làm sạch) cho đến khi 3 cấu hình đọc ra cùng một lưới.
- Chỉ publish khi: 3 lượt OCR khớp từng ô, bảng bắt đầu ở bậc 0 hoặc 1, nhãn lane không dài quá
  30 ký tự, và qua mọi kiểm tra chung. Không đạt thì học khu về `no_schedule` (tìm lại sau 90 ngày),
  không vào hàng chờ xem tay, vì chủ dự án không duyệt tay được hàng trăm bảng (D-034).
- Đo trên bộ chuẩn đổi thành ảnh (30 tài liệu, 200 dpi): 2 bảng publish, 153/153 ô đúng, 0 bảng sai
  lọt. Hai lượt khớp nhau vẫn có thể cùng sai (Douglas: một chữ số; Bullitt: mất hai cột), nên cần
  ba lượt và các luật trên. Tỉ lệ ra bảng thấp là chấp nhận được: thà ít bảng còn hơn bảng sai.
- Tài liệu scan đã xử lý trước khi có OCR được đọc lại: `known.json` kèm cờ `scanned`, và
  `known_documents` coi bản scan chưa qua OCR là chưa đọc.

## D-038: Link bảng lương tìm tay cho học khu lớn

- Ngày: 2026-11-13. Chủ dự án đồng ý ("hướng 1"). Nhiều học khu lớn không ra bảng vì website chặn
  bot ở trang chủ, đã đổi domain, hoặc trang lương nằm sâu hơn 25 trang crawl.
- `pipeline/sources/schedule-urls.csv` (`nces_id,url,note`): link tìm bằng tay tới tệp bảng lương
  hoặc trang "salary schedules" chính thức của học khu (không dùng bản chép của bên thứ ba).
  Học khu có link thì pipeline bỏ bước crawl, tải thẳng link (trang HTML thì thử lần lượt tối đa 6
  tệp trên trang, xếp theo độ giống bảng lương của chữ trên link; trang không có tệp nào thì crawl
  tối đa 8 trang từ đó như một website học khu. Lô 1 cho thấy chỉ lấy tệp đầu thì
  hay trúng bảng hiệu trưởng hoặc bảng nhân viên); robots.txt của host tài liệu vẫn được tuân thủ.
  Thư hiệp hội giáo viên (bên ký hợp đồng lương với học khu) được dùng khi học khu không đăng.
- `pdf-pipeline-run.json` có `seeded_only: true` để chạy riêng các học khu trong tệp, mọi trạng thái.

## D-039: Bảng Florida theo hiệu suất, bảng hiệu trưởng và quản lý

- Ngày: 2026-11-13. Chủ dự án quyết định sau khi so với salaryschedule.org (đối thủ phủ khoảng
  21,6 triệu học sinh, mình 12,6 triệu; khác biệt chủ yếu ở 101 học khu trên 20 nghìn học sinh).
- Lấy bảng lương giáo viên theo hiệu suất của Florida (lương khởi điểm theo năm kinh nghiệm và
  phần tăng), hiển thị "như học khu công bố".
- Lấy bảng lương hiệu trưởng, hiệu phó và quản lý (thay phần "bỏ lương hiệu trưởng" của bàn
  giao). Vẫn bỏ superintendent: mỗi học khu một người, đăng ra là lương của một cá nhân.
- Không lấy dữ liệu từ site đối thủ: robots.txt của họ chặn bot AI và bot thu thập, bảng là công
  sức đọc của họ. Chỉ dùng tài liệu chính thức của học khu.
- Bộ đọc bỏ qua số phụ bên cạnh lương năm: lương ngày, phụ cấp dưới 10.000 USD, ô "-" (Garland
  ISD in phụ cấp giữ chân giáo viên TRA giữa hai cột lương).

## D-040: Thử https và www khi không lấy được robots.txt

- Ngày: 2026-11-13. 572 học khu chưa có dữ liệu (2,19 triệu học sinh) dừng ở "không truy cập
  được robots.txt (lỗi mạng): coi như cấm", phần lớn vì NCES còn ghi địa chỉ `http://www.` cũ.
- Trước khi crawl, pipeline thử lần lượt: địa chỉ NCES, bản https, bản https có/không `www.`,
  rồi bản gốc có/không `www.`; lấy địa chỉ đầu tiên tải được robots.txt. Không biến thể nào trả
  lời thì vẫn coi như cấm (RFC 9309). robots.txt của địa chỉ được chọn vẫn được tuân thủ.

## D-041: Bảng in từng khoản lương dưới mỗi bậc; bộ đọc phiên bản 6

- Ngày: 2026-11-13. Seattle in dưới mỗi bậc các dòng Base Pay, Contractual Days, Tech Days,
  Responsibility/Incentive và TOTAL. Trang có từ 3 dòng TOTAL trở lên thì mỗi bậc chỉ giữ dòng
  TOTAL (lương năm), các dòng khoản lương khác bỏ.
- Bộ đọc lên phiên bản 6 (`layout-text@6`…) để lượt chạy sau đọc lại cả tài liệu không đổi
  (Garland ISD, Seattle) bằng các thay đổi của D-039 và D-041.

## D-042: Ghi lại trang chủ khi crawl không thấy gì

- Ngày: 2026-11-14. Lượt toàn quốc: khoảng 4.700 học khu "không thấy tài liệu", phần lớn chỉ đọc
  1–8 trang vì trang chủ không có link nào mang chữ việc làm/lương để đi tiếp.
- Khi không thấy tài liệu, chi tiết ghi địa chỉ cuối của trang chủ, cỡ trang, số link, số link
  cùng site và số link được đi tiếp; `work.json` giữ 40 link đầu của trang chủ để xem vì sao.

## D-043: Website học khu thay cho địa chỉ NCES đã chết

- Ngày: 2026-11-14. 1.127 học khu chưa có bảng mà site NCES không truy cập được (không tải được
  robots.txt hoặc trang chủ). Với 128 học khu (0,72 triệu học sinh, gồm Chicago, Fort Bend,
  Chesterfield), website các trường của học khu (D-035) trỏ về một tên miền khác, nên dùng tên
  miền đó: `district-websites.csv` có thêm cột `replaces_nces`; dòng có `1` thay địa chỉ NCES.
- Nhiều học khu còn lại (Baltimore County, Lee, Albuquerque) có tên miền vẫn sống nhưng chặn bot
  ở tầng mạng; đó là ý của họ, không lách.

## D-044: Nhận diện trang bảng lương rộng hơn; bậc chạy ngược; bộ đọc phiên bản 7

- Ngày: 2026-11-14. Trong 3.361 học khu "tải được tệp nhưng không giống bảng lương", phần lớn
  tệp đúng là không phải bảng lương (sổ tay, kế hoạch). Số bị bỏ sót có ba dạng:
  - Bảng một cột ngắn (Tyler ISD: 11 dòng năm kinh nghiệm): trang có ít nhất 8 số tiền, chữ
    bậc/năm, chữ giáo viên và chữ "salary" được nhận.
  - Bảng không ghi chữ "step" (Muhlenberg "From Top 16…1", Carroll hàng A–Z): trang có ít nhất 40
    số tiền, chữ "salary" và chữ lane hoặc giáo viên được nhận.
  - Bậc in từ lớn xuống nhỏ: bộ đọc theo chiều của các hàng đầu, không cắt bảng ở mỗi hàng.
- Bộ mẫu chuẩn không đổi (24 publish, 2560/2560, 0 sai). Thử trên lô 0 của lượt toàn quốc: thêm
  3/141 học khu đọc được. Bộ đọc lên @7 để lượt sau đọc lại tài liệu đã biết.

## D-045: Tự publish bảng một cột chỉ thiếu tên cột

- Ngày: 2026-11-14. Hàng chờ có 245 lý do mở; 13 bảng chỉ có lý do "Nhãn lane thiếu tên:
  'salary'": bảng một cột (thường ở Texas) mà tiêu đề cột là "Salary". Hai bộ đọc đã khớp, số
  liệu không đổi, nên tự publish như nguồn (D-034). Các lý do khác của lane_label (nhiều lane cùng
  nhãn) vẫn để người xem vì không biết cột nào là bằng cấp nào.

## D-046: Bảng lương viết thành bảng HTML trên trang web

- Ngày: 2026-11-14. Nhiều học khu lớn (Frisco, Plano…) đăng thang lương thành bảng HTML trên trang
  Compensation, không có tệp PDF; pipeline trước đây chỉ đọc tệp nên crawl hết trang vẫn "không
  thấy tài liệu".
- Trang có bảng `<table>` qua được `score_page` (như một trang PDF có bảng lương) được coi là tài
  liệu loại `html`: lưu lại chỉ các bảng đó và tiêu đề trang (để hash không đổi theo menu,
  script, giờ), phân loại như tài liệu khác và đọc bằng `html-cells` (cùng cách đọc ô như Word).
- Khi crawl gặp trang như vậy thì trang đó thành ứng viên tài liệu.
