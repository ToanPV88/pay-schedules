# Bàn giao — 2026-11-15

Tệp này ghi trạng thái dự án để một phiên Claude khác làm tiếp. Đọc thêm `AGENTS.md`,
`docs/PLAN.md` và `docs/DECISIONS.md` (mới nhất là D-058).

## 1. Ràng buộc chủ dự án đã đặt

- **Bí mật:** không tự nhập token, mật khẩu hay API key vào bất kỳ đâu; chủ dự án tự làm. Secret
  chỉ nằm trong GitHub Secrets, và chỉ đặt vào `env` của đúng bước dùng nó.
- **Dữ liệu cá nhân:** không thu thập hay hiển thị tên, lương của cá nhân. Không lấy lương
  superintendent. Bảng lương hiệu trưởng và quản lý thì được lấy (D-039, chưa làm).
- **Nguồn:** repo travienphi chỉ được đọc. Tôn trọng robots.txt. Không dùng API AI trả phí (D-022).
- **Cách làm:** không tự tạo subagent khi chưa được yêu cầu. Mỗi công đoạn kết thúc bằng PR, và
  chỉ squash-merge khi mọi check xanh. Production chỉ chạy commit đã có trên `main`.
- **Phút GitHub Actions:** chủ dự án đã duyệt chạy không cần hỏi lại, với mục tiêu có càng nhiều
  học khu càng tốt. Repo đang để public để có phút chạy; nhắc chủ dự án chuyển về private khi
  xong.
- **Ngôn ngữ:** trả lời và viết tài liệu bằng tiếng Việt; giao diện site bằng tiếng Anh.

## 2. Số liệu hiện tại

Thống kê lúc 2026-11-15 07:45 (giờ Việt Nam):

| Chỉ số | Giá trị |
|---|---|
| Học khu có bảng đã publish | 2.686 |
| Học sinh được phủ | 14,97 triệu / 46,07 triệu (32,5%) |
| Bảng đang chờ duyệt tay | 385 |
| Michigan / Ohio | 165 / 205 học khu |

Các mốc trước: 2.515 học khu (31,7%), rồi 2.651 (32,3%) sau khi thêm Michigan (D-056) và các
học khu Ohio trùng tên (D-055).

## 3. Cách chạy

### Pipeline PDF

1. Sửa `pipeline/pdf-pipeline-run.json` qua một PR rồi merge. Các khóa:
   - `limit`, `state`;
   - `rerun`: danh sách trạng thái được chạy lại;
   - `shards` (tối đa 20), `deadline_minutes` (tối đa 270);
   - `seeded_only`, `ids_file` (`pipeline/sources/*.csv`);
   - `manual_release`, `reread_drafts`.
2. Đẩy commit trên main lên nhánh chạy:
   `git push -f origin origin/main:run/pdf-pipeline-production`.
   Nhánh này phải trỏ vào commit đã có trên main, nếu không lượt chạy hỏng.
3. Lượt chạy mới xếp hàng sau lượt đang chạy. Chỉ một lượt được chờ; lượt mới hơn thay thế nó.
4. Kết quả của mỗi lô nằm ở Release `docs-production-<ngày>-<run id>-s<N>`, gồm `report.md`,
   `docs.tar`, `work.json` và `extractions.json`.

### Thống kê

Nhánh `stats-tmp` có workflow thống kê đã sửa: dòng `ALL` có thêm quận và thành phố, dòng `MISS`
in mọi học khu còn thiếu. **Không ghi đè nhánh này bằng main.**

- Chạy:
  `git checkout stats-tmp && git commit --allow-empty -m stats && git push -f origin stats-tmp:run/stats`.
- Đọc log của job: các dòng `ALL` (nces, bang, tên, học sinh, số bảng publish, quận, thành phố),
  các dòng `MISS` (nces, bang, tên, học sinh, website, trạng thái, chi tiết) và dòng
  `open_review (bảng)`.

### Merge PR trong phiên này

- `gh pr create` từng lỗi. Dùng
  `gh api repos/ToanPV88/pay-schedules/pulls -f title=… -f head=… -f base=main -f body=…`.
- Chờ `commits/<sha>/check-runs` có danh sách không rỗng và không còn kết quả `null`, rồi
  `gh api -X PUT …/pulls/<n>/merge -f merge_method=squash`.

### Kiểm tra trước khi merge

- Từ thư mục `pipeline/`: `ruff format`, `ruff check`, `mypy src`, `pytest`.
- Bộ chuẩn: `python -m pay_pipeline.cli pdf-eval --gold gold --docs <thư mục tài liệu gold> --report …`
  phải giữ 24 publish, 2.560/2.560 ô đúng, 0 bảng sai.

## 4. File chủ dự án tải tay (D-051)

Danh sách đã giao nằm trong `docs/reports/tai-tay/`. Chủ dự án cũng có bản Sheet trong tài khoản
Claude cũ, nhưng tài khoản mới có thể không mở được.

| Tệp | Nội dung | Trạng thái |
|---|---|---|
| `dot-1-150-hoc-khu.csv` | 150 học khu | Đã nhận và chạy: 26/129 học khu lên site |
| `dot-2-120-hoc-khu-lon.csv` | 120 học khu lớn nhất còn thiếu (8,4 triệu học sinh) | Chủ dự án đang tải |
| `dot-3-229-hoc-khu.csv` | 229 học khu kế tiếp (4,1 triệu học sinh) | Chưa tải |
| `tat-ca-con-thieu-9737.csv` | Mọi học khu còn thiếu, xếp theo số học sinh | Tên file có tiền tố `T`, ví dụ `T0001_…` |

Khi nhận một file .zip:

1. Giải nén vào một thư mục mới. Ghép STT trong tên file với mã NCES theo danh sách của đợt đó.
2. Gói các file thành `files.tar` và đẩy lên một nhánh riêng
   `manual-files/manual-<YYYYMMDD>-<tên>`. Nhánh này chỉ chứa `files.tar` và không merge vào main.
   Xem nhánh mẫu `manual-files/manual-20261114-tai-tay-1`.
3. Thêm `pipeline/sources/manual-<YYYYMMDD>-<tên>.csv` với các cột `nces_id,file,url`. `file` là
   đường dẫn trong tar; `url` là link gốc của file, tức nguồn hiển thị trên site. Nếu chủ dự án
   gửi `download_report.csv` thì lấy link từ đó.
4. Qua PR, đặt `manual_release` bằng `manual-<YYYYMMDD>-<tên>` (khớp
   `^manual-[0-9]{8}-[a-z0-9-]+$`), merge, rồi đẩy nhánh chạy.

## 5. Việc vừa làm (2026-11-14 đến 15)

- **D-055, Ohio:** học khu trùng tên được khớp với hợp đồng SERB theo cột County (4 chữ đầu tên
  quận).
- **D-056, Michigan:** dùng kho hợp đồng Mackinac Center. 456 học khu được thêm vào
  `schedule-urls.csv`; danh sách chạy là `pipeline/sources/michigan-mackinac-1.csv`.
- **D-057, OCR:**
  - dò tối đa 160 trang, gồm 40 trang đầu và các trang cuối;
  - nhận số bậc in phía trên hàng số tiền;
  - sửa số bậc đọc sai trong dãy tăng đều;
  - bỏ phiếu từng ô giữa các lượt OCR;
  - bộ đọc OCR lên @2.
- **D-058:** hợp đồng nhiều năm lấy năm mới nhất nhưng không quá năm học kế tiếp. Bộ đọc văn bản
  lên @10, và đã đọc lại các bảng nháp.
- **Lượt chạy:** cả hai lượt D-057 (run 43652095086) và D-058 (run 43653695839) đều thành công.
  Số liệu ở mục 2 đã gồm kết quả của chúng.

## 6. Nguồn đã xem nhưng chưa dùng

- **New York — SeeThroughNY:** danh sách hợp đồng lấy qua `/tools/...`, bị robots.txt chặn.
- **Pennsylvania:** chưa tìm thấy kho hợp đồng công khai nào còn hoạt động.
- **Connecticut — ConnCAN:** dữ liệu chỉ có tới năm 2015-16, quá cũ.
- **Maryland — MSDE:** file `2026-professional-salary-schedules-a.pdf` có bảng lương của cả 24
  học khu. robots.txt cho phép `*` với `use=reference`, nhưng chặn ClaudeBot và các bot AI, nên
  phiên trước không đọc qua Chrome. Nếu làm, hãy viết bộ nhập theo tiểu bang và để pipeline tự
  tải file (tham khảo `schedules/state_import.py`).
- **Michigan, 66 học khu:** hợp đồng Mackinac không kèm bảng lương (ví dụ Hartland), nên phải lấy
  bảng từ site học khu hoặc tải tay.

## 7. Việc nên làm tiếp

1. **Xử lý file tải tay** đợt 2 và đợt 3 khi chủ dự án gửi (mục 4).
2. **Hàng chờ duyệt (385 bảng).** Lỗi hay gặp:
   - `double_extraction`: hai bộ đọc ra lưới khác nhau;
   - `school_year`;
   - `lane_label`: nhãn cột lẫn chữ;
   - `step_start`.

   Nên xem nhóm nào sửa được bằng bộ đọc.
3. **OCR bản scan Michigan:** nhiều bảng vẫn chỉ có 1/3 lượt OCR khớp. Bảng lớn đọc ra các mảnh
   khác nhau ở mỗi lượt, ví dụ Swan Valley.
4. **D-039:** bảng lương hiệu trưởng và quản lý (không lấy superintendent).
5. **Bảng trải nhiều trang**, và bộ nhập Maryland (mục 6).

## 8. Dọn dẹp khi xong

- **Xóa các nhánh tạm:** `manual-files/manual-20261114-tai-tay-1`, `tmp/coverage-compare`,
  `stats-tmp` (giữ lại nếu còn cần thống kê), và các nhánh `run/*` cũ nếu muốn.
- **Chuyển repo về private.**
