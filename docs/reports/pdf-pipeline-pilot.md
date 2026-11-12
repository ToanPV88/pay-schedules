# Pipeline PDF (Công đoạn 5): chạy thử và nghiệm thu

Ngày: 2026-11-12/13. Môi trường chạy thử: CSDL preview. Đọc bảng tất định, không gọi API AI (D-022).

## Nghiệm thu theo PLAN

| Tiêu chí | Ngưỡng | Kết quả |
|---|---|---|
| Bộ chuẩn 30 bảng nhập tay | 30 | 30 (`pipeline/gold/*.json`; tài liệu nằm trong Release, có sha256) |
| Ô đúng trên các bảng sẽ publish | ≥ 99% | 2435/2435 = 100% trên 23 bảng sẽ publish; 7 bảng chờ xem tay (xem `pdf-gold-2026-11-12.md`) |
| Bảng sai lọt qua Validate | 0 | 0 |
| Chạy lại không tạo bản ghi trùng | không trùng | đạt: test `test_load_is_idempotent_and_consistent`, `test_known_document_is_not_processed_again` và test nạp hai lần trong `test_pdf_pipeline.py`; chạy thử lần 2–4 trên cùng CSDL preview không thêm bảng nào cho học khu đã có |

Bộ chuẩn chạy bằng workflow `pdf-eval.yml` (không secret, tải tài liệu từ Release và kiểm sha256). 15 bảng
đầu dựng từ tài liệu dùng để kiểm tra chéo ở Công đoạn 4 và đối chiếu với số liệu của bang; 15 bảng sau
lấy từ chạy thử, đối chiếu bằng mắt trên ảnh trang. Bộ chuẩn không đo nhãn lane và tiêu đề; hai thứ này
được xem tay trên các bảng của chạy thử (mục "Lỗi đã sửa" bên dưới).

## Chạy thử 100 học khu

Bốn lần chạy trên preview, thứ tự học khu đông học sinh nhất trước. Lần sau chạy lại các học khu chưa
tìm được bảng, với bộ đọc đã sửa theo lỗi của lần trước. Tổng hợp: 158 học khu khác nhau (trạng thái
cuối của mỗi học khu; các bảng đã đọc được đọc lại tại chỗ bằng bộ đọc cuối cùng: ô không đổi, bốn bảng chuyển sang xem tay do kiểm tra mới).

| Lần chạy (Release) | Học khu | Tìm thấy tài liệu | Đọc được bảng | Publish | Xem tay |
|---|---:|---:|---:|---:|---:|
| docs-preview-20261112-43259387073 | 100 | 30 | 18 | 10 | 8 |
| docs-preview-20261112-43261614750 | 100 | 25 | 6 | 4 | 2 |
| docs-preview-20261112-43263799987 | 120 | 33 | 11 | 8 | 3 |
| docs-preview-20261112-43266894335 | 120 | 27 | 5 | 3 | 2 |

Trạng thái cuối của 158 học khu:

| Trạng thái | Học khu | Tỉ lệ |
|---|---:|---:|
| published | 21 | 13% |
| review (chờ xem tay) | 15 | 9% |
| no_schedule (có tài liệu, không phải/không đọc được bảng) | 67 | 42% |
| no_candidates (không thấy link tài liệu) | 37 | 23% |
| unreachable (robots.txt chặn hoặc lỗi mạng) | 10 | 6% |
| no_website (NCES không có website) | 8 | 5% |

- Tỉ lệ tìm thấy tài liệu giống bảng lương giáo viên: khoảng 25–30% mỗi lần chạy.
- Tỉ lệ có bảng (publish hoặc xem tay) trên số học khu: 36/158 = 23%; trong đó qua Validate: 21/36.
- Chi phí trung bình mỗi học khu: 0 USD tiền model. Thời gian GitHub Actions: khoảng 10–12 phút cho
  100 học khu (job `run` 7–12 phút, `archive` và `load` mỗi job dưới 1 phút).
- Bảng publish ở chạy thử: Austin, Adams 12, Baldwin County, Berkeley, Brownsville, Charleston,
  Clear Creek, Detroit, Douglas County CO, Ector County, El Paso, Fort Worth, Jefferson County CO,
  Katy, Manatee, Memphis-Shelby, Montgomery County MD, Pinellas, Weber, Williamson County, Ysleta
  (một số trong đó là bảng tuyển mới theo năm kinh nghiệm, dạng phổ biến ở Texas).
  Oklahoma City (bảng 2023-24) và Clark County, Hillsborough, San Antonio chuyển sang xem tay sau khi
  thêm các kiểm tra ở mục dưới.

## Lô đầu trên production

Sau khi merge (commit 19db2e3), lô 100 học khu đông nhất trên CSDL production
(Release `docs-production-20261112-43271718628`, khoảng 12 phút Actions):

| Học khu | Tìm thấy tài liệu | Đọc được bảng | Publish | Xem tay | no_schedule | no_candidates | no_website | unreachable |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 38 | 22 | 13 | 9 | 42 | 21 | 8 | 7 |

Kiểm tra trượt ở 9 bảng chờ xem tay: `step_start` 4, `lane_label` 3, `monotonic_lane` 2,
`schedule_scope` 1, `school_year` 1, `double_extraction` 1 (một bảng có thể trượt nhiều kiểm tra).
Học khu đã có bảng từ file của bang (CA, KY) không vào hàng đợi.

## Các kiểu lỗi (học khu không ra bảng)

| Kiểu | Học khu | Ghi chú |
|---|---:|---|
| Tài liệu tải về không phải bảng lương giáo viên | 29 | bảng nhân viên hỗ trợ, phụ cấp, thông báo; bảng giáo viên nằm ở chỗ khác hoặc trong trang HTML |
| Có tài liệu nhưng không đọc được bảng bậc × lane | 19 | bảng đặt cạnh nhau trên một trang, bảng không có nhãn bậc ở đầu hàng, sách lương nhiều chục trang |
| Không thấy link tài liệu trên website | 37 | bảng nằm trong trang HTML, trong cổng tuyển dụng, hoặc sâu hơn 2 tầng |
| Trang tài liệu trung gian vẫn không ra tệp | 12 | Google Drive/Docs bị robots.txt chặn, trình xem tài liệu cần JavaScript |
| robots.txt chặn hoặc lỗi mạng ở trang chủ | 10 | tôn trọng robots.txt, không vượt |
| PDF dạng ảnh quét | 3 | cần OCR, chưa làm |
| Lỗi tải tệp | 4 | HTTP 4xx/5xx |

## Lỗi đã sửa trong lúc chạy thử

- Trang tài liệu trung gian (Apptegy, Finalsite: `/documents/.../<id>`) dựng link tệp bằng JavaScript:
  tìm URL tệp trong script/JSON của trang (Hillsborough, Manatee, El Paso, San Antonio tìm được tài liệu).
- Năm học viết bằng gạch Unicode (`2026‐2027`), chữ giãn (`2 0 2 5 – 2026`), `FY26-27` (trước đó đọc
  nhầm thành 2025-26: Berkeley).
- Lương giờ 4 chữ số thập phân in cạnh lương năm (Hillsborough).
- Nhãn lane lẫn chữ đơn vị (`Hourly Rate`, `ANNUAL(1)`), ngày hiệu lực, chữ của tiêu đề bảng (Douglas
  County: `General Compensation MA + 15` thành `MA + 15`).
- Bảng chỉ cho một nhóm giáo viên (thuê trước một ngày, giáo viên ngoài lớp học): xếp sau bảng chung,
  nếu chỉ có nó thì chờ xem tay với kiểm tra `schedule_scope` (Hillsborough, San Antonio).
- Nhãn lane lẫn chữ của đoạn văn bên cạnh bảng: chờ xem tay (`lane_label`, Clark County).
- Bảng trên website cũ hơn hai năm học: chờ xem tay (`school_year`, Oklahoma City 2023-24).
- Đổi bộ đọc thì tăng số phiên bản (`layout-text@4`...): tài liệu đã đọc bằng bản cũ được đọc lại dù
  sha256 không đổi.

## Vận hành

- Lô: `pdf-pipeline.yml`, chạy bằng cách đẩy lên `run/pdf-pipeline-preview` hoặc
  `run/pdf-pipeline-production` (tham số trong `pipeline/pdf-pipeline-run.json`: `limit`, `state`,
  `rerun`). Production chỉ chạy từ commit đã có trên `main`.
- Điểm lưu: bảng `district_pipeline`; lô sau bỏ qua học khu chưa đến hạn chạy lại (ví dụ `no_schedule`
  90 ngày, `published` 180 ngày, `review` chờ người).
- Trang xem tay: Worker `pay-schedules-review` (HTTP Basic, secret `REVIEW_PASSWORD`, D-021). Duyệt một
  bảng thì publish, tính lại `district_summary` và xếp học khu vào hàng chờ xóa cache (D-023).
- Học khu không có bảng: trang web hiện "schedule not found", link website học khu, noindex
  (Công đoạn 6).

## Mở rộng

PLAN: chỉ mở rộng khi chủ dự án duyệt chi phí. Tiền model là 0; chi phí còn lại là phút GitHub Actions
của repo private: khoảng 12 phút cho 100 học khu, tức khoảng 1.500–2.000 phút cho toàn bộ học khu có
website, chia nhiều tháng nếu dùng hạn mức miễn phí.
