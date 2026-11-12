# Khảo sát tái sử dụng travienphi (Công đoạn 0)

Ngày khảo sát: 2026-11-12. Repo: `ToanPV88/hospital-price-ai` (site travienphi.com), commit
`3d8881e683ffb075b99863908ad1c8cf8723551d`, đọc ở chế độ chỉ đọc, không sửa tệp nào.

Nguồn đọc: mã trong `src/`, `.github/`, `tests/`, cùng `docs/status.md`, `docs/architecture.md`,
`docs/d1.md`, `docs/site.md`, `docs/extraction.md`, `docs/operations.md`, `AGENTS.md` và các ADR
0002, 0009, 0011, 0012, 0019, 0029, 0030, 0034, 0035, 0037.

## 1. Năm phát hiện làm thay đổi kế hoạch

1. **travienphi không dùng LLM.** ADR-0002 cấm API AI trả phí. Trích xuất là tất định: pdfplumber
   cho PDF có lớp chữ, openpyxl/xlrd cho Excel, BeautifulSoup cho HTML, Tesseract cho bản scan. Vì
   vậy không có "prompt và schema trích xuất" nào để viết lại; phần này phải **viết mới**. Ngược
   lại, các extractor tất định dùng được ngay làm **lớp đầu** cho bảng lương (bảng nhỏ, có lớp chữ),
   chỉ gửi LLM khi lớp đầu thất bại. Cách này giảm chi phí ở Công đoạn 5.
2. **Hạ tầng phục vụ là Cloudflare Pages + Pages Functions + D1, không phải Workers.** Pipeline là
   Python chạy trên GitHub Actions. Tài liệu gốc lưu trong GitHub Release riêng tư, không có R2.
3. **Deploy không dùng wrangler và cố ý tắt bản xem trước.** Cloudflare Pages kéo nhánh `site` qua
   tích hợp Git (ADR-0012). Kế hoạch mới cần URL xem trước cho mỗi PR, nên phần deploy phải **viết
   lại**, không "giữ" như dự kiến.
4. **D1 gói Free giới hạn 100.000 dòng ghi mỗi ngày** và đã định hình cả kiến trúc travienphi: hai
   CSDL A/B luân phiên, nạp mỗi ngày một tệp, gộp giá vào cột JSON để giảm số dòng. Sau đó chủ dự án
   vẫn phải lên Workers Paid. Bảng `cells` của kế hoạch mới có thể lên hàng triệu dòng, nên Công đoạn
   2 cần chọn sớm: dùng Workers Paid ngay, hoặc lưu ma trận lương dạng JSON mỗi bảng (xem §8).
5. **FTS5 chạy được trên D1:** travienphi tìm kiếm bằng bảng ảo FTS5 trên D1 thật, 0,3–8 ms mỗi lần
   tìm, CPU của mã 1–5 ms (dưới giới hạn 10 ms của gói Free). Câu hỏi "D1 có hỗ trợ FTS5 không" ở
   Công đoạn 2 đã có câu trả lời thực nghiệm. Lưu ý: bảng FTS5 không lưu nội dung thì không xóa được
   mục, travienphi phải để mục mồ côi và luôn nối lại với bảng chính.

## 2. Stack thực tế

| Lớp | travienphi đang dùng |
| --- | --- |
| Ngôn ngữ pipeline | Python ≥ 3.11, Pydantic v2, mypy strict, ruff, pytest (533 hàm kiểm thử) |
| Ngôn ngữ web | JavaScript thuần, không framework, không bước build; một tệp Function 2.627 dòng |
| CSDL nội bộ | SQLite qua SQLAlchemy 2 + Alembic (có nhánh PostgreSQL, không dùng thật) |
| CSDL phục vụ | Cloudflare D1: `hpa-meta` (con trỏ CSDL đang dùng), `hpa-a`, `hpa-b` |
| Kho tài liệu gốc | Thư mục cục bộ theo SHA-256, đóng gói vào GitHub Release riêng tư `fetch-<run>` |
| Trạng thái giữa các lần chạy | GitHub Release `state-*` (ảnh chụp SQLite + bộ nhớ đệm trích xuất) |
| Lịch chạy | GitHub Actions: `fetch.yml` quý một lần (`17 2 1 1,4,7,10 *`), `d1-sync.yml` hằng ngày |
| Host | Cloudflare Pages dự án `tra-gia-vien-phi`, tên miền travienphi.com |
| Deploy | Job `publish` đẩy nhánh `site`; Pages kéo nhánh đó qua tích hợp Git |
| Dịch vụ ngoài | Workers AI (Qwen3-30B) chỉ để hiểu câu hỏi chatbot; Turnstile; Web Analytics; Google Fonts |
| OCR | Tesseract cục bộ (`vie` đọc ô, `eng` đọc lại chữ số) |
| Biến môi trường | `HPA_DATA_DIR`, `HPA_DATABASE_URL`, `HPA_USER_AGENT`, `HPA_CONTACT_EMAIL`, `HPA_D1_*`, `HPA_EXTRACT_WORKERS`; secret `CLOUDFLARE_API_TOKEN` (chỉ quyền D1), `TURNSTILE_SECRET_KEY` (trên Pages) |
| Chi phí | Giới hạn chi tiêu GitHub Actions 7 USD/tháng; Workers Paid 5 USD/tháng từ 2026-11-06 |

## 3. Luồng dữ liệu

```text
seeds/hospitals.csv + sources.csv (người duyệt từng nguồn)
  → hpa fetch (PoliteFetcher, robots.txt, ≥5 giây/yêu cầu)  → raw/<sha256> + retrievals/*.jsonl
  → Release fetch-<run> (chỉ tài liệu mới)
  → hpa pipeline: extract → normalize (hồ sơ tài liệu, cờ chất lượng) → db load (SQLite)
  → public snapshot (SQLite chỉ đọc, chỉ giá qua quy tắc hiển thị)
  → hpa d1 export (tệp SQL ≤ 90.000 dòng ghi) → d1-sync.yml nạp vào CSDL đang rảnh → đổi con trỏ
  → Pages Function đọc D1, trả API và trang HTML
```

Mọi bước ghi một lần và chạy lại được. Bộ nhớ đệm trích xuất có khóa (SHA-256, tên extractor,
phiên bản), nên đổi extractor bắt buộc tăng phiên bản.

## 4. Render, URL, sitemap

- Giao diện chính là **ứng dụng một trang**, định tuyến bằng `#` (`#tim-kiem?q=…`, `#bv/<id>`,
  `#ma/<code>`). Nội dung chỉ hiện sau khi JavaScript gọi `/api/*`.
- Từ ADR-0035 (2026-11-10), Function dựng thêm trang HTML phía server: `/benh-vien`,
  `/benh-vien/<mã>`, `/gia/<tên>`, `/huong-dan/*`, các trang thông tin và `/sitemap.xml`. Các trang
  này chỉ hiện **mẫu** giá (tối đa 30 dòng), có `Cache-Control` 1 giờ.
- Công tắc index duy nhất là `.github/site-indexable`; Function đọc `robots.txt` của bản dựng để
  quyết định `noindex`. Site mở cho Google ngày 2026-11-10, chưa gắn quảng cáo.
- Chống thu thập (ADR-0034): API từ chối `*.pages.dev` và yêu cầu `cross-site`; tối đa 10 trang mỗi
  lần tìm; giới hạn lượt theo IP trong Worker và trên zone; Bot Fight Mode; Turnstile cho chatbot.

## 5. Schema và tìm kiếm

- SQLite nội bộ: `hospitals`, `sources`, `documents`, `retrievals`, `document_headers`,
  `profile_versions`, `load_runs`, `price_observations` (bất biến, khóa `record_id` +
  `content_hash`), `observation_spans`, `review_events`, `quality_issues`.
- D1: `service_groups` (mỗi dòng một nhóm tên, các giá nằm trong cột JSON `prices` lưu gọn),
  `service_fts` (FTS5 không lưu nội dung), `hospitals`, `documents`, `hospital_documents`, `codes`,
  `labels`, `flags`, `meta`, `_hpa_load`.
- Tìm kiếm: bỏ dấu tiếng Việt, mỗi từ khớp tiền tố, mở rộng từ viết tắt, xếp hạng theo bốn tầng
  (khớp đúng, cụm ở đầu, cụm ở giữa, đủ từ), phân trang bằng con trỏ `rowid` thay OFFSET. Người dùng
  không chèn được cú pháp FTS5 vì chỉ chữ và số lọt vào truy vấn.

## 6. Phần gắn chặt với Việt Nam

- Ngôn ngữ: toàn bộ chuỗi giao diện, thông báo lỗi, tài liệu, bài hướng dẫn (`GUIDES`), trang thông
  tin (`INFO_MAIN`) nằm trong mã Function hoặc `static/*.html`.
- Tiền: `normalization/price.py` (`parse_vnd`, dấu chấm hàng nghìn, "nghìn đồng").
- Chữ: `fold()` bỏ dấu tiếng Việt, danh sách từ viết tắt (XN, CT, MRI), từ đồng nghĩa ("sinh mổ").
- Mã dịch vụ: `normalization/codes.py`, so sánh cùng mã (`/api/compare`).
- Loại giá: BHYT / không BHYT / theo yêu cầu / chênh lệch; quy tắc nhận tiêu đề cột trong
  `extraction/mapping.py` và `columnKind` trong Function.
- Văn bản nhà nước: nghị quyết HĐND dùng chung nhiều bệnh viện (ADR-0024, 0026), dự thảo chưa ký
  (`extraction/draft.py`), hồ sơ tài liệu về hiệu lực.
- Địa lý: `PROVINCE_OF`, `PROVINCE_FORMER` (tỉnh sau sáp nhập), `site/provinces.py`.
- OCR: mô hình `vie`; `quality/ocr_names.py` nhận từ tiếng Việt đọc sai.
- Chatbot: toàn bộ bộ hiểu câu hỏi bằng quy tắc tiếng Việt.

## 7. Bài học đã có

**Lỗi trích xuất hay gặp** (đều đã có cách xử lý trong `pdf_table.py` và `ocr.py`):

- Glyph khoảng trắng vẽ đè lên chữ số làm "195.000" thành "1 95.000".
- Glyph vẽ hai lần cùng chỗ (giả in đậm) làm "630,000" thành "663300,,000000".
- Font nhúng thiếu bảng ToUnicode cho ra `(cid:17)`; giải mã từ chính chương trình font.
- Chữ xoay chéo của dấu ký số hoặc watermark đè lên bảng, **có thể chứa họ tên người ký**; bị bỏ
  trước khi dò bảng. Điểm này liên quan trực tiếp tới nguyên tắc 3 (không thu tên cá nhân).
- Tiêu đề cột tách hai dòng; bảng nối qua nhiều trang (dùng lại tiêu đề trang trước); bảng rộng tách
  ngang qua trang (chưa giải được); bảng không kẻ ô (extractor riêng `pdf-text-columns`).
- Trang HTML đổi SHA-256 ở mỗi lần tải dù nội dung không đổi; xử lý bằng dấu vân tay nội dung.
- Ô giá dạng "400.000/lần"; giá là công thức ("0,3 lần giá…"); đơn vị nghìn đồng: không đoán, để
  trống và gắn cờ.

**Cách kiểm tra:**

- `trace-check`: đọc lại tài liệu bằng cách khác extractor (lớp chữ của trang) để xác nhận tên và số
  tiền có thật ở đúng vị trí. Lần đầu: 254/255 mẫu khớp. Cách này dùng lại được để kiểm kết quả LLM.
- OCR: chữ số đọc hai lần bằng hai mô hình, phải khớp từng chữ số và lần hai có độ tin cậy ≥ 90, nếu
  không giá bị chặn. Đây là phiên bản tất định của "trích hai lần độc lập rồi so khớp".
- Rà soát tay mẫu ngẫu nhiên phân tầng: 40/40 giá OCR đúng, khoảng tin cậy Wilson 95% là
  91,2–100%. Cách báo số đo này nên dùng cho bộ chuẩn 30 bảng ở Công đoạn 5.
- Cảnh báo tất định sau mỗi lần chạy (`ops/health.py`): tải lỗi > 20% nguồn, một bệnh viện mất
  ≥ 50% bản ghi, thay đổi giá ≥ ±50%, hồ sơ không còn khớp bằng chứng.

**Chi phí và vận hành:**

- Không có chi phí LLM, nên **không có số đo chi phí mỗi tài liệu** để mang sang. Số đo đó phải lấy
  từ lần chạy thử 100 học khu.
- Chi phí thật nằm ở phút GitHub Actions: lần chạy đầy đủ khoảng 62 phút, xử lý lại 15–20 phút;
  bước trích xuất 29 phút, chuẩn hóa từng mất 50 phút trước khi tối ưu (ADR-0030).
- Bộ nhớ: hơn 1 triệu bản ghi trong RAM vượt 7 GB của runner; phải xử lý theo luồng. SQLite từng
  phình lên 13 GB (ADR-0029).
- Tăng phiên bản extractor làm mọi tài liệu phải đọc lại, từng vượt giới hạn 90 phút của job; phải
  thêm hạn mức trang nâng cấp mỗi lần chạy.
- Một số website chặn máy chạy GitHub (DNS, IP nước ngoài, `robots_unreachable`); phải có luồng
  chủ dự án tải tay có ghi URL gốc (ADR-0021).
- Duyệt từng nguồn bằng tay (ADR-0013) chạy được với ~190 bệnh viện nhưng không mở rộng được tới
  hàng nghìn học khu; kế hoạch mới dùng Discover tự động có điểm tin cậy là hợp lý.

## 8. Bảng quyết định

Giả định: pipeline giữ Python trên GitHub Actions, web chạy trên Cloudflare (Workers hoặc Pages
Functions) + D1. Nếu chủ dự án chọn viết pipeline bằng TypeScript, mọi dòng "Giữ"/"Sửa" của mã
Python dưới đây chuyển thành "Viết lại, dùng làm tài liệu tham khảo".

Nghĩa của các quyết định: **Giữ** là chép gần nguyên văn; **Sửa** là chép rồi đổi phần gắn với Việt
Nam hoặc với hạ tầng cũ; **Viết lại** là chỉ lấy ý tưởng; **Bỏ** là không mang sang.

### Tệp ở gốc repo

| Module | File | Quyết định | Lý do |
| --- | --- | --- | --- |
| Quy tắc cho agent | `AGENTS.md` | Sửa | Khung tốt (quy tắc dữ liệu, bí mật, Git, chi phí AI, báo cáo cuối tác vụ). Bỏ các ngoại lệ ADR của Việt Nam, thêm nguyên tắc 1–7 của PLAN |
| Giới thiệu | `README.md` | Viết lại | Nội dung riêng về bệnh viện Việt Nam |
| Cấu hình Python | `pyproject.toml`, `Makefile` | Sửa | Giữ cấu hình ruff, mypy strict, pytest; bỏ phụ thuộc không dùng (alembic, psycopg, fastapi, xlrd nếu không cần) |
| Biến môi trường | `.env.example` | Sửa | Giữ cách khai tên biến không kèm giá trị; đổi tiền tố và danh sách biến |
| Bỏ qua của Git | `.gitignore` | Giữ | Mẫu chặn bí mật và dữ liệu dùng được nguyên |

### `.github/`

| Module | File | Quyết định | Lý do |
| --- | --- | --- | --- |
| CI | `workflows/ci.yml` | Sửa | Giữ lint + typecheck + test, chỉ Python 3.11 cho PR (ADR-0020). Thêm kiểm thử JS, migration trên D1 preview, deploy bản xem trước |
| CI PostgreSQL | `workflows/ci-db.yml` | Bỏ | Không dùng PostgreSQL |
| Kiểm tra tài liệu | `workflows/docs.yml` | Giữ | PR chỉ sửa tài liệu không tốn phút chạy test |
| Tải và xử lý | `workflows/fetch.yml` | Viết lại | Giữ cách chia job theo quyền (chỉ job tải ra Internet, chỉ một job có quyền ghi) và nhóm `concurrency`. Bỏ trạng thái qua Release và bước đẩy nhánh `site` |
| Nạp D1 | `workflows/d1-sync.yml` | Bỏ | Cơ chế A/B nạp nhiều ngày chỉ cần ở gói Free. Nếu ở lại gói Free thì xem lại dòng này |
| Deploy web | `workflows/site-api.yml` | Viết lại | Kế hoạch mới deploy bằng wrangler, có bản xem trước cho mỗi PR |
| Script Release | `scripts/download-archives.sh`, `latest-snapshot.sh`, `download-manual-docs.sh` | Bỏ | Gắn với kho trạng thái trong GitHub Release |
| Công tắc vận hành | `d1-plan`, `d1-snapshot`, `site-mode`, `state-exclude.txt` | Bỏ | Gắn với A/B và Release |
| Công tắc index | `site-indexable` | Viết lại | Ý tưởng một công tắc duy nhất vẫn đúng, nhưng kế hoạch mới mở index theo từng bang, nên công tắc nằm trong D1 hoặc cấu hình theo bang |

### Thư mục dữ liệu và tài liệu

| Module | File | Quyết định | Lý do |
| --- | --- | --- | --- |
| Dữ liệu cục bộ | `data/` | Bỏ | Bị Git bỏ qua; thay bằng R2 và D1 |
| Tài liệu thiết kế | `docs/*.md` | Viết lại | Nội dung riêng; giữ cách tổ chức một tệp cho mỗi mảng (fetching, extraction, operations) |
| Quyết định kiến trúc | `docs/adr/` | Giữ (mẫu) | Mẫu ADR (bối cảnh, quyết định, phương án đã cân nhắc, hệ quả) dùng cho `docs/DECISIONS.md`. Đọc lại ADR-0002, 0019, 0029, 0030, 0034 khi làm Công đoạn 1, 2, 5, 6 |
| Biên bản lần chạy | `docs/runs/` | Giữ (thói quen) | Mỗi lần chạy thử ghi số đo và lỗi; cần cho báo cáo 100 học khu ở Công đoạn 5 |
| Chọn nhóm thử | `docs/pilot/` | Bỏ | Riêng bệnh viện |
| Nhật ký rà soát | `reviews/` | Sửa | Ý tưởng nhật ký chỉ ghi thêm và phát lại lên dữ liệu mới dùng cho nhật ký thay đổi của Công đoạn 9; chuyển từ JSONL sang bảng D1 |
| Danh mục | `seeds/` | Bỏ | Danh mục học khu lấy từ NCES (Công đoạn 3), không duyệt tay từng nguồn |

### `src/hospital_price_ai/`

| Module | File | Quyết định | Lý do |
| --- | --- | --- | --- |
| domain | `models.py`, `enums.py`, `validation.py` | Viết lại | Mô hình giá phẳng của Việt Nam. Giữ các bất biến: bản ghi không sửa, bắt buộc có nguồn và vị trí, thời điểm có múi giờ |
| domain | `review.py` | Sửa | Chuyển trạng thái bằng hàm thuần, mã tự động không đặt được trạng thái cao; đổi sang draft → validated → published → superseded |
| domain | `profile.py` | Sửa | Mỗi thông tin cấp tài liệu phải có trích dẫn nguyên văn và số trang. Dùng cho năm học và số ngày hợp đồng |
| domain | `catalog.py` | Bỏ | Danh mục duyệt tay |
| registry | `loader.py`, `catalog.py`, `delegation.py`, `proposals.py` | Bỏ | Quy trình duyệt nguồn bằng tay |
| registry | `profiles.py` | Bỏ | Phần còn dùng được nằm ở `extraction/evidence.py` |
| acquisition | `robots.py` | Giữ | Đánh giá robots.txt theo RFC 9309, không gắn với Việt Nam, đã có kiểm thử |
| acquisition | `policy.py` | Giữ | Chặn tắt robots.txt và chặn khoảng cách dưới 1 giây. Mặc định travienphi là 5 giây; PLAN cho phép 1 giây |
| acquisition | `http.py` | Sửa | Bộ tải lịch sự: thử lại theo `Retry-After`, giới hạn kích thước, yêu cầu có điều kiện. Đổi User-Agent và nơi lưu sang R2 |
| acquisition | `fetch_log.py` | Sửa | Nhật ký mọi lần tải; chuyển đích ghi |
| acquisition | `fetch.py`, `runner.py` | Sửa | Đổi đầu vào từ danh mục nguồn đã duyệt sang danh sách học khu và URL ứng viên |
| acquisition | `site_discovery.py` | Sửa | Khung cho bước Discover: đọc trang chủ, xác nhận tên đơn vị có trên trang, đi theo liên kết có từ khóa. Thay từ khóa tiếng Việt bằng "salary schedule", "certificated", "negotiated agreement"… |
| acquisition | `discovery.py` | Sửa | Tìm liên kết tài liệu trên trang danh sách; đổi từ khóa và đuôi tệp |
| acquisition | `manual.py` | Sửa | Luồng tải tay có SHA-256 cho học khu chặn máy chạy; nối với trang xem tay nội bộ |
| storage | `raw_store.py` | Sửa | Kho ghi một lần theo SHA-256; đổi sang khóa R2 |
| extraction | `base.py` | Giữ | Giao thức extractor có `name` và `version` |
| extraction | `pdf_table.py` | Sửa | Lớp đầu cho PDF có lớp chữ. Các xử lý glyph trùng, font thiếu ToUnicode, chữ chéo là chung cho mọi PDF; bỏ quy tắc tiêu đề tiếng Việt |
| extraction | `html_table.py`, `csv_extractor.py` | Giữ | Không gắn với Việt Nam |
| extraction | `excel.py`, `xls.py` | Giữ | Cần khi dữ liệu bang (Kentucky) hoặc học khu đăng Excel |
| extraction | `docx_table.py` | Giữ | Thỏa ước lao động thường đăng dạng Word |
| extraction | `pdf_text_columns.py` | Viết lại | Bám vào cột "STT" của bảng Việt Nam; lấy ý tưởng xếp cột theo tọa độ |
| extraction | `ocr.py` | Sửa (tùy chọn) | Quy tắc đọc chữ số hai lần là điểm đáng giữ. Nếu PLAN dùng model đọc ảnh cho bản scan thì để module này làm phép kiểm tra độc lập hoặc bỏ |
| extraction | `mapping.py` | Viết lại | Ánh xạ dòng thô thành giá phẳng theo tiêu đề tiếng Việt; bảng lương cần ánh xạ ma trận bậc × bằng cấp |
| extraction | `evaluate.py` | Sửa | `trace-check` dùng lại để kiểm từng ô LLM trả về có thật trên trang PDF |
| extraction | `evidence.py` | Sửa | Kiểm trích dẫn nguyên văn có trong tài liệu đã lưu |
| extraction | `draft.py` | Viết lại | Nhận văn bản dự thảo; bảng lương cũng có bản "tentative" hay "proposed" cần loại, nhưng quy tắc khác |
| extraction | `json_records.py` | Bỏ | Trường hợp riêng của một trang bệnh viện |
| extraction | `pipeline.py` | Sửa | Giữ bộ nhớ đệm theo (SHA-256, extractor, phiên bản), chạy song song, ghi kết quả theo luồng, hạn mức trang mỗi lần chạy |
| normalization | `price.py`, `text.py`, `codes.py` | Bỏ | Tiền VND, bỏ dấu tiếng Việt, mã dịch vụ Việt Nam. Viết `parse_usd` mới theo cùng nguyên tắc: mơ hồ thì trả rỗng |
| normalization | `profiles.py`, `pipeline.py` | Viết lại | Gắn với hồ sơ hiệu lực của văn bản Việt Nam |
| quality | `checks.py` | Sửa | Giữ khung `Issue`/`Severity` và nguyên tắc chỉ gắn cờ, không sửa. Viết các kiểm tra mới của bước Validate; phép phát hiện bất thường median/MAD dùng cho kiểm tra lệch giữa các năm |
| quality | `ocr_names.py` | Bỏ | Nhận từ tiếng Việt đọc sai |
| review | `sheet.py`, `log.py` | Sửa | Thay phiếu Excel bằng trang xem tay nội bộ; giữ nhật ký chỉ ghi thêm và phát lại |
| publishing | `gate.py`, `reference.py` | Sửa | Cổng mặc định từ chối, liệt kê mọi lý do chặn; áp vào quy tắc published và quy tắc index |
| publishing | `snapshot.py` | Bỏ | Cần vì CSDL nội bộ là SQLite cục bộ; kế hoạch mới ghi thẳng D1 và lọc bằng `status` |
| publishing | `d1.py` | Sửa | Lấy phần chia câu lệnh dưới 100 KB, ước tính dòng ghi, tệp kê khai có `check_sql` để đối chiếu sau khi nạp. Bỏ phần gộp nhóm giá |
| publishing | `d1_sync.py` | Bỏ | Nạp A/B từng ngày; xem lại nếu ở lại gói Free |
| db | `schema.py`, `engine.py`, `load.py`, `migrations/` | Viết lại | SQLAlchemy + Alembic cho SQLite; D1 dùng tệp migration SQL qua wrangler |
| db | `history.py` | Viết lại | Ý tưởng chuỗi phiên bản theo thời gian dùng cho trang lịch sử các năm |
| ops | `pipeline.py` | Sửa | Điều phối các bước và in tiến độ từng bước |
| ops | `health.py` | Sửa | Cảnh báo tất định sau mỗi lần chạy; khớp với Công đoạn 9 |
| ops | `state.py` | Bỏ | Lưu trạng thái qua GitHub Release |
| api | `app.py` | Bỏ | FastAPI chỉ dùng nội bộ |
| site | `build.py` | Viết lại | Dựng ứng dụng một trang và kiểm từng byte trước khi đẩy nhánh `site` |
| site | `static/*` (`index.html`, `app.js`, `app-api.js`, `chat.html`, `style.css`, biểu tượng) | Viết lại | Ứng dụng một trang tiếng Việt, định tuyến bằng `#`; PLAN cần trang render phía server cho từng học khu |
| site | `functions/api/[[path]].js` | Sửa | Tách tệp 2.627 dòng. Giữ: truy vấn FTS5 an toàn, phân trang bằng con trỏ, giới hạn lượt, phiên Turnstile, từ chối `pages.dev` và `cross-site`, `esc`/`safeUrl`, khung trang HTML, sitemap, công tắc index. Bỏ: chatbot, tỉnh/thành, `TOPICS`, `GUIDES`, từ đồng nghĩa, giải nén giá |
| site | `functions/[[path]].js` | Bỏ | Chỉ chuyển tiếp sang tệp trên |
| site | `provinces.py` | Bỏ | Tỉnh/thành Việt Nam |
| cấu hình | `config.py` | Sửa | Đọc biến môi trường, không có giá trị mặc định cho bí mật, `redacted()` khi in log |
| CLI | `cli.py` | Sửa | Giữ cấu trúc lệnh con; đổi tên lệnh và bỏ lệnh không dùng |

### `tests/`

| Module | File | Quyết định | Lý do |
| --- | --- | --- | --- |
| Kiểm thử bất biến repo | `test_repo_consistency.py` | Sửa | Chặn secret trong workflow, chặn `innerHTML`/`eval`, bảo đảm bước kiểm tra chạy trước khi đẩy. Rất hợp với nguyên tắc 6–7 |
| Kiểm thử tải | `test_storage_and_acquisition.py`, `test_fetching.py` | Sửa | Đi cùng `robots.py`, `http.py`, `raw_store.py` |
| Kiểm thử extractor | `test_extraction.py`, `test_xls.py`, `test_docx_table.py`, `test_ocr.py`, `test_pdf_text_columns.py` | Sửa | Đi cùng extractor được giữ; fixture giả lập đổi sang bảng lương giả lập |
| Kiểm thử Function | `js/api.test.mjs`, `test_pages_api.py`, `test_site_api.py` | Sửa | Cách chạy `node --test` trên `node:sqlite` thay cho D1 dùng lại được |
| Còn lại | `test_phase*.py`, `test_d1_*.py`, `test_db*.py`, `test_catalog.py`, `test_chat*`, … | Bỏ | Đi cùng module bị bỏ hoặc viết lại |

## 9. Đối chiếu dự kiến trong PLAN.md

| Phần của travienphi | Dự kiến | Kết luận sau khảo sát |
| --- | --- | --- |
| Khung pipeline tải, đọc, kiểm tra, lưu | Sửa | **Xác nhận.** Thêm: extractor tất định làm lớp đầu trước LLM |
| Prompt và schema trích xuất | Viết lại | **Bác bỏ.** Không có prompt nào; đây là phần **viết mới** |
| Lưu link tài liệu gốc và nhãn "chưa kiểm chứng" | Giữ | **Xác nhận về nguyên tắc**, mã thì Sửa: nguồn nằm trong snapshot và JSON nén của D1 |
| Tìm kiếm và bộ lọc | Sửa | **Xác nhận.** FTS5 trên D1 đã chạy thật; tìm theo tên học khu đơn giản hơn tìm tên dịch vụ |
| Trang danh sách và trang chi tiết | Sửa | **Đổi thành Viết lại.** Phần lớn là ứng dụng một trang; chỉ lấy khung trang HTML và sitemap |
| Hỏi đáp AI | Bỏ ở giai đoạn đầu | **Xác nhận** |
| Quy trình deploy GitHub → Cloudflare | Giữ | **Bác bỏ, đổi thành Viết lại.** travienphi dùng tích hợp Git, tắt bản xem trước, không có wrangler. Chỉ giữ bài học: token quyền tối thiểu, ghim action theo SHA |
| Trang giới thiệu, hướng dẫn, miễn trừ | Viết lại bằng tiếng Anh | **Xác nhận.** Nội dung đang nằm trong mã JS (`INFO_MAIN`, `GUIDES`); nên tách ra tệp nội dung |

## 10. Đề xuất cho các quyết định còn mở

- **Stack:** giữ Python cho pipeline để dùng lại bộ tải, robots.txt, extractor và kiểm thử. Web viết
  mới trên Cloudflare + D1; tận dụng các đoạn trong tệp Function. Trước Công đoạn 1, cần kiểm tra
  khuyến nghị hiện hành của Cloudflare giữa Workers (kèm static assets) và Pages Functions, vì PLAN
  muốn wrangler và bản xem trước cho mỗi PR. Chủ dự án chốt.
- **Gói D1:** ước tính thô, khoảng 13.000 học khu (số chính xác ở Công đoạn 3) nhân 100–300 ô mỗi
  bảng là 1–4 triệu dòng `cells` cho một năm học, cộng chỉ mục. Ở gói Free (100.000 dòng ghi mỗi
  ngày) cần vài tuần để nạp. Hai cách: dùng Workers Paid ngay từ đầu, hoặc lưu ma trận lương thành
  JSON trong `schedules` và chỉ tách `cells` ở CSDL nội bộ. Nên chốt trong Công đoạn 2.
- **Trạng thái công bố:** travienphi không bao giờ tự đặt trạng thái "đã xác minh"; mọi giá hiện
  nhãn "chưa xác minh". PLAN cho bảng tự chuyển sang published sau Validate. Đây là thay đổi chủ ý
  về mức rủi ro; nên ghi rõ trên `/methodology` rằng "validated" là kiểm tra tự động, không phải
  người xác nhận.
- **Phút GitHub Actions:** travienphi đã chạm giới hạn chi tiêu và phải tối ưu nhiều lần. Ngân sách
  phút Actions nên được tính cùng ngân sách API ở Công đoạn 5.
