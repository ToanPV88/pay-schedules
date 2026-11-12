# AGENTS.md — Quy tắc cho trợ lý AI và người làm trên repo này

Thứ tự ưu tiên khi xung đột: **an toàn dữ liệu > tính đúng > yêu cầu tác vụ > tốc độ**.
Khung tệp này lấy từ travienphi (`docs/REUSE_AUDIT.md` §8).

## 1. Đọc trước khi làm

`docs/PLAN.md` (phần "Bối cảnh và nguyên tắc" và công đoạn đang làm), `docs/DECISIONS.md`,
`docs/REUSE_AUDIT.md`. Mỗi phiên làm đúng một công đoạn; trước khi code, liệt kê tệp sẽ tạo hoặc sửa.

## 2. Quy tắc dữ liệu (bắt buộc)

1. **Không bịa dữ liệu.** Không tạo tên học khu, URL, năm học, số ngày hợp đồng hay con số lương.
   Không đoán URL tài liệu. Ô nào thiếu thì để trống và ghi rõ.
2. **Mỗi con số truy được về nguồn:** URL, thời điểm tải (có múi giờ), SHA-256 tài liệu, số trang.
3. **Không thu tên hay lương của từng cá nhân.** Chỉ bảng lương của đơn vị. Tài liệu có danh sách
   nhân viên kèm lương thì không trích phần đó và báo lại.
4. **Mã tự động không tự nâng mức tin cậy:** dữ liệu chưa qua Validate không được index và phải có
   nhãn trạng thái.
5. **Không sửa đè bảng đã published:** bản mới thành bảng mới, bản cũ chuyển `superseded`; mọi lần
   sửa tay ghi giá trị trước, sau và lý do.
6. **Dữ liệu kiểm thử là giả lập có nhãn rõ:** tên miền `example.invalid`, tên học khu chứa "Test".
   Không chép tài liệu thật vào `tests/fixtures/`.

## 3. Thu thập

- Chỉ tài liệu công khai, không đăng nhập. Không vượt CAPTCHA, tường đăng nhập hay robots.txt.
- Mọi lần tải đi qua `pay_pipeline.acquisition.CrawlPolicy`: robots.txt bắt buộc, tối thiểu 1 giây
  giữa hai yêu cầu tới cùng tên miền, User-Agent có thông tin liên hệ.
- Kiểm thử mặc định không gọi mạng; kiểm thử cần mạng gắn `@pytest.mark.network`.

## 4. Bí mật

- Không đưa token, mật khẩu, khóa riêng vào mã, tài liệu, test, log hay commit message.
- Bí mật của Worker đặt bằng `wrangler secret put`; bí mật của CI đặt trong GitHub Actions secrets.
  Hiện chỉ có `CLOUDFLARE_API_TOKEN`; thêm secret mới phải ghi vào `docs/DECISIONS.md`.
- Trong workflow, secret chỉ nằm ở `env` của bước gọi wrangler; không `set -x`.
  `pipeline/tests/test_repo_consistency.py` kiểm tra các quy tắc này.

## 5. Git và quy trình

- Làm trên nhánh riêng (`feat/…`, `fix/…`, `docs/…`); mọi thay đổi vào `main` qua pull request.
- Không force-push, không viết lại lịch sử nhánh chung.
- Trước khi kết thúc: chạy `npm run lint && npm run typecheck && npm test` và, trong `pipeline/`,
  `uv run ruff check src tests && uv run mypy && uv run pytest`. Báo kết quả thật.
- Không sửa CI để "xanh giả". Action mới ghim theo commit SHA, quyền token ở mức tối thiểu.
- Repo travienphi (`ToanPV88/hospital-price-ai`) chỉ được đọc.

## 6. Mã nguồn

- Web: TypeScript strict, Hono, HTML render phía server bằng helper `html` (tự escape). Không dùng
  `innerHTML` với dữ liệu.
- Pipeline: Python ≥ 3.12, type hints đầy đủ, `mypy --strict` sạch. Định danh và docstring bằng
  tiếng Anh; tài liệu cho chủ dự án bằng tiếng Việt; giao diện site bằng tiếng Anh.
- Đổi hành vi của extractor thì tăng `version` của nó.
- Thêm phụ thuộc: ghi lý do vào `docs/DECISIONS.md`.

## 7. Chi phí

- Không gọi API trả phí (LLM, OCR đám mây) khi chủ dự án chưa duyệt model và ngân sách
  (PLAN, "Rủi ro và quyết định còn mở").
- Tài khoản Cloudflare dùng chung với travienphi (D-001): kiểm tra hạn mức của cả tài khoản.

## 8. Khi không chắc

Dừng và hỏi khi: có thể xóa hoặc ghi đè dữ liệu; cần quyết định một nguồn có được thu thập không;
cần công bố hoặc mở index; cần thêm dịch vụ trả phí.

## 9. Báo cáo cuối tác vụ

Tệp đã tạo/sửa; lệnh kiểm tra đã chạy và kết quả; đối chiếu từng tiêu chí nghiệm thu; việc chưa làm
được và lý do; bước tiếp theo.
