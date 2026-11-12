# Kế hoạch dựng site tra cứu bảng lương giáo viên Mỹ

Nov 12, 2026 · @OanhNK

> Bản trong repo của tài liệu kế hoạch (Project "tra cưu lương"). Quyết định đã chốt ghi ở
> `docs/DECISIONS.md`; kết quả khảo sát travienphi ở `docs/REUSE_AUDIT.md`.

## Bối cảnh và nguyên tắc

Site mới là công cụ tra cứu bảng lương giáo viên (salary schedule) của từng học khu công lập ở Mỹ, giao diện tiếng Anh, sống bằng quảng cáo hiển thị. Nó dựng lại trên mô hình của travienphi.com: thu tài liệu công khai, máy đọc, lưu có cấu trúc, tra cứu kèm link gốc.

- **Người dùng:** giáo viên Mỹ đang so sánh học khu, người sắp vào nghề, người chuyển bang.
- **Giá trị riêng:** bảng lương đầy đủ theo bậc (step) và bằng cấp (lane), máy tính lương, so sánh học khu lân cận, link tài liệu gốc.
- **Stack mục tiêu:** Cloudflare Workers + D1 + R2, GitHub + GitHub Actions, Claude viết code.

Nguyên tắc bắt buộc trong mọi công đoạn:

1. Mọi con số phải truy được về tài liệu gốc: lưu URL, ngày tải, số trang.
2. Không suy đoán, không nội suy. Ô nào thiếu thì để trống và ghi rõ.
3. Chỉ đăng bảng lương của học khu. Không thu thập hay hiển thị tên và lương của từng giáo viên.
4. Dữ liệu chưa qua kiểm tra tự động thì không được Google index và phải gắn nhãn trạng thái.
5. Mỗi trang phải có thứ mà PDF gốc không có: máy tính, so sánh, lịch sử các năm.
6. Repo travienphi chỉ được đọc, không sửa. Site mới nằm ở repo riêng.
7. Khi tải tài liệu từ website học khu: tuân thủ robots.txt và giới hạn tốc độ.

Chưa làm ở giai đoạn đầu: hỏi đáp AI, tài khoản người dùng, trường tư.

## Cách giao việc cho Claude

Giao từng công đoạn một; mỗi công đoạn kết thúc bằng tiêu chí nghiệm thu và một pull request riêng.

- Xuất tài liệu này ra Markdown và lưu vào repo mới dưới tên `docs/PLAN.md`, để Claude đọc lại ở mỗi phiên.
- Công đoạn 0 chạy trong repo travienphi ở chế độ chỉ đọc. Từ Công đoạn 1 trở đi chạy trong repo mới.
- Thứ tự phụ thuộc: 0 → 1 → 2 → 3 → 4 → 6 → 5 → 7 → 8 → 9 → 10. Website (6) làm trước pipeline PDF (5) để site ra mắt được với dữ liệu California và Kentucky.
- Mọi quyết định kỹ thuật Claude tự đưa ra phải ghi vào `docs/DECISIONS.md` kèm lý do.
- Chỗ nào tài liệu này ghi "Claude kiểm tra" là thông tin tôi chưa xác minh; Claude phải tra tài liệu chính thức trước khi code.

Lời nhắc mẫu cho mỗi phiên:

```text
Đọc docs/PLAN.md, phần "Bối cảnh và nguyên tắc" và "Công đoạn N".
Thực hiện Công đoạn N. Trước khi code, liệt kê file sẽ tạo hoặc sửa.
Không làm việc của công đoạn khác.
Kết thúc: chạy test, đối chiếu từng tiêu chí nghiệm thu, rồi mở pull request.
```

## Công đoạn 0: khảo sát repo travienphi

Kết quả của công đoạn này là một bảng "giữ / sửa / viết lại / bỏ" cho từng module của travienphi, làm căn cứ cho mọi công đoạn sau.

Việc cần làm:

1. Liệt kê stack thực tế: framework, runtime, database, nơi host, cách deploy, biến môi trường, dịch vụ ngoài (LLM API, OCR).
2. Mô tả luồng dữ liệu hiện tại: tài liệu vào từ đâu, bước nào đọc, lưu vào bảng nào, trang nào đọc ra.
3. Xác định cách render: phía server hay phía client, mỗi bệnh viện hoặc dịch vụ có URL riêng không, có sitemap không.
4. Liệt kê schema hiện có và cách tìm kiếm đang hoạt động.
5. Đánh dấu phần gắn chặt với ngữ cảnh Việt Nam: ngôn ngữ, mã dịch vụ, loại giá.
6. Ghi lại bài học đã có: kiểu lỗi trích xuất hay gặp, cách kiểm tra, chi phí cho mỗi tài liệu.

Đầu ra: file `docs/REUSE_AUDIT.md` trong repo mới, dạng bảng với các cột Module, File, Quyết định, Lý do.

Dự kiến ban đầu của tôi, cần Claude xác nhận hoặc bác bỏ bằng code thật:

| Phần của travienphi | Dự kiến |
| --- | --- |
| Khung pipeline tải, đọc, kiểm tra, lưu | Sửa |
| Prompt và schema trích xuất | Viết lại |
| Lưu link tài liệu gốc và nhãn "chưa kiểm chứng" | Giữ |
| Tìm kiếm và bộ lọc | Sửa |
| Trang danh sách và trang chi tiết | Sửa |
| Hỏi đáp AI | Bỏ ở giai đoạn đầu |
| Quy trình deploy GitHub → Cloudflare | Giữ |
| Trang giới thiệu, hướng dẫn, miễn trừ | Viết lại bằng tiếng Anh |

Nghiệm thu:

- Bảng phủ mọi thư mục cấp cao của repo, mỗi dòng có lý do.
- Không file nào trong repo travienphi bị sửa.

## Công đoạn 1: khởi tạo repo và hạ tầng

Xong công đoạn này, một repo mới deploy được trang thử lên Cloudflare từ nhánh main và có bản xem trước cho mỗi pull request.

1. Tạo repo mới. Sao chép các module được đánh dấu "Giữ" trong `REUSE_AUDIT.md`.
2. Dựng cấu trúc thư mục:

```text
/apps/web            Worker render trang và API
/packages/db         schema, migration, hàm truy vấn
/pipeline            discover, fetch, classify, extract, validate, publish
/data/seeds          file nhập ban đầu (NCES, California, Kentucky)
/docs                PLAN.md, REUSE_AUDIT.md, DECISIONS.md
/.github/workflows   CI, deploy, lịch chạy pipeline
```

3. Tạo tài nguyên Cloudflare: một Worker cho web, hai database D1 (production và preview), một bucket R2 lưu bản sao tài liệu gốc.
4. Cấu hình `wrangler.toml` với hai môi trường. Khóa bí mật đặt qua `wrangler secret` và GitHub Actions secrets, không commit vào repo.
5. Dựng CI: lint, typecheck, test, chạy migration trên D1 preview, deploy bản xem trước cho mỗi pull request, deploy production khi merge vào main.
6. Gắn tên miền, bật HTTPS, chuyển hướng www về tên miền chính.
7. Trang được render từ D1 trong Worker rồi cache, không xuất hàng nghìn file tĩnh. Lý do: Cloudflare Pages bản miễn phí giới hạn số file mỗi site.
8. Nếu travienphi dùng stack khác Workers + D1, ghi quyết định giữ hay chuyển vào `DECISIONS.md` trước khi code.

Nghiệm thu:

- Pull request tạo ra URL xem trước; merge vào main thì production cập nhật.
- Migration rỗng chạy được trên cả hai database.
- Không có khóa bí mật nào trong repo hoặc trong log CI.

## Công đoạn 2: mô hình dữ liệu

Bảng lương là ma trận bậc × bằng cấp theo từng năm học, nên schema tách "bảng lương" khỏi "ô lương" và luôn gắn mỗi bảng với tài liệu nguồn. Đây là khác biệt lớn nhất so với danh sách giá phẳng của travienphi.

| Bảng | Mỗi dòng là | Cột chính |
| --- | --- | --- |
| `states` | một bang | code, name, slug |
| `districts` | một học khu | nces\_id, name, slug, state, city, county, website, enrollment, lat, lng, active |
| `district_neighbors` | một cặp học khu gần nhau | district\_id, neighbor\_id, distance\_km |
| `source_documents` | một tài liệu đã tải | district\_id, url, fetched\_at, sha256, r2\_key, mime, page\_count |
| `schedules` | một bảng lương | district\_id, school\_year, schedule\_type, title, contract\_days, source\_document\_id, source\_page, status, confidence |
| `lanes` | một cột bằng cấp | schedule\_id, position, label\_raw, lane\_normalized |
| `steps` | một bậc | schedule\_id, position, label\_raw, years\_experience |
| `cells` | một ô lương | schedule\_id, step\_id, lane\_id, amount\_cents, note |
| `stipends` | một khoản phụ cấp ngoài bảng | schedule\_id, name, amount\_cents, condition |
| `extraction_runs` | một lần trích xuất | source\_document\_id, model, prompt\_version, raw\_output, cost\_usd |
| `review_queue` | một việc cần người xem | schedule\_id, reason, resolved\_at |
| `district_summary` | số liệu tóm tắt để so sánh nhanh | district\_id, school\_year, start\_ba, ma\_step10, max\_salary |

Quy tắc:

- `status` đi theo thứ tự draft → validated → published → superseded. Chỉ bảng published mới hiện trên trang được index.
- `schedule_type` nhận các giá trị teacher, substitute, classified. Giai đoạn đầu chỉ làm teacher.
- Tiền lưu bằng số nguyên (cents), không dùng số thực.
- Nhãn gốc giữ nguyên văn trong `label_raw`; giá trị chuẩn hóa (BA, BA+15, MA, MA+30, PhD) nằm ở cột riêng.
- Một học khu có thể có nhiều bảng trong một năm. Khóa duy nhất: district\_id, school\_year, schedule\_type, title.
- Index cho slug học khu, bang, cặp district\_id + school\_year, và tìm theo tên. Claude kiểm tra D1 có hỗ trợ full-text search (FTS5) không trước khi dùng.
- `district_summary` được tính lại sau mỗi lần publish.

Chừa sẵn cho Công đoạn 10, làm ngay trong migration đầu tiên: bảng `districts` có thêm cột `employer_type` (mặc định school\_district); bảng `schedules` có thêm `pay_basis` (annual, monthly, hourly, daily) và `hours_per_year`; một bảng lương được phép không có lane. Ba điểm này giúp mở sang nghề khác mà không phải viết lại schema.

Nghiệm thu:

- Migration chạy sạch trên database trống.
- Nhập tay ba bảng lương mẫu (một bảng chuẩn, một bảng có nhãn lane lạ, một bảng chỉ có bậc không có lane) và test đọc ra đúng từng ô.

## Công đoạn 3: danh mục học khu

Nhập toàn bộ học khu công lập từ bộ dữ liệu Common Core of Data (CCD) của NCES, để mỗi học khu có trang và mã định danh ổn định trước khi có bảng lương.

1. Tải file danh mục Local Education Agency mới nhất của CCD. Claude tìm đúng file và năm, rồi ghi URL vào `DECISIONS.md`.
2. Lọc: giữ học khu thông thường (regular local school district) đang hoạt động. Loại supervisory union, service agency, cơ quan cấp bang và liên bang.
3. Map cột: mã LEAID thành `nces_id`, cùng tên, bang, địa chỉ, website, loại. Bổ sung sĩ số từ file membership.
4. Tạo slug ổn định theo mẫu `/{state}/{district-slug}`. Hai học khu trùng tên trong một bang thì thêm tên quận.
5. Tính học khu lân cận: cùng quận, cộng các học khu gần nhất theo tọa độ. Lưu vào `district_neighbors`.
6. Script chạy lại được nhiều lần mà không tạo trùng. Học khu đã đóng thì đánh dấu inactive, không xóa.

Nghiệm thu:

- Số học khu mỗi bang khớp với bảng tổng hợp của NCES; chỗ lệch có giải thích.
- Không có slug trùng.
- Kiểm tra tay 20 học khu ngẫu nhiên: tên, bang và website đúng.

## Công đoạn 4: dữ liệu có sẵn của California và Kentucky

Hai bang này có dữ liệu bảng lương do Sở Giáo dục bang công bố, nên nhập trước để site có nội dung thật ngay khi ra mắt, chưa cần pipeline PDF.

California:

- Nguồn: trang [Certificated Salaries & Benefits (J-90)](https://cde.ca.gov/ds/fd/cs/) của Sở Giáo dục California.
- File tải về là gói tự giải nén (.EXE) kèm Readme. Giải nén bằng công cụ dòng lệnh, không chạy file.
- Đọc Readme trước để tìm bảng chứa ô lương theo cột và bậc. Readme các năm trước mô tả nhóm file TSAL với cột `TS3_Col` và `TS3_Step`.
- Map mã CDS của California sang `nces_id`.
- J-90 là khảo sát tự nguyện: bản 2024–25 phủ 83,05% học khu và văn phòng giáo dục quận. Học khu thiếu thì chuyển sang pipeline PDF.
- Từ năm tài chính 2025–26, bang chuyển sang hệ thống [C-90](https://www.cde.ca.gov/FG/sf/c90.asp) và dự kiến công bố dữ liệu trước 26/2/2027. Viết importer tách riêng phần đọc file để đổi định dạng dễ.

Kentucky:

- Nguồn: trang [School District Personnel Information](https://www.education.ky.gov/districts/FinRept/Pages/School%20District%20Personnel%20Information.aspx) của Sở Giáo dục Kentucky, mục certified salary schedules.
- Claude kiểm tra định dạng file (Excel hay PDF) rồi viết importer tương ứng.

Chung cho cả hai:

- Mỗi importer ghi một dòng `source_documents` (URL file của bang, ngày tải, sha256) cho mỗi file nguồn.
- Bảng nhập vào phải qua bộ kiểm tra tự động mô tả ở Công đoạn 5 (bước Validate) trước khi publish. Viết bộ kiểm tra này ngay ở đây.
- Kiểm tra chéo 10 học khu mỗi bang với PDF trên website học khu. Nếu lệch, ưu tiên tài liệu của học khu khi nó mới hơn.
- Tìm thêm bang có dữ liệu tập trung: Claude tìm từng bang và ghi kết quả vào `docs/STATE_SOURCES.md`.

Nghiệm thu:

- Từ 95% học khu có trong file của bang được nhập thành công; phần còn lại có lý do.
- Mỗi bảng có năm học và link nguồn.
- Có báo cáo số học khu còn thiếu ở mỗi bang.

## Công đoạn 5: pipeline PDF

Pipeline biến website của một học khu thành bảng lương đã kiểm tra qua sáu bước. Bước nào thất bại thì bảng vào hàng chờ xem tay, không được đăng.

1. **Discover.** Tìm URL tài liệu bảng lương của học khu. Thử lần lượt: sitemap và trang Human Resources hoặc Employment trên website học khu; tìm kiếm web với mẫu "\[district\] certified salary schedule \[school year\]"; thỏa ước lao động tập thể nếu bảng lương nằm trong đó. Lưu mọi ứng viên kèm điểm tin cậy.
2. **Fetch.** Tải file, tuân thủ robots.txt, tối đa một request mỗi giây cho mỗi tên miền, User-Agent có thông tin liên hệ. Lưu bản gốc vào R2 và ghi sha256. File có sha256 không đổi thì bỏ qua.
3. **Classify.** Xác định tài liệu có phải bảng lương giáo viên không, thuộc năm học nào, bảng nằm ở trang nào. Loại bảng lương quản lý và nhân viên hỗ trợ.
4. **Extract.** Gửi đúng các trang chứa bảng cho LLM và yêu cầu JSON theo schema cố định: school\_year, contract\_days, lanes, steps, cells, stipends, notes. PDF dạng ảnh quét thì dùng model đọc ảnh. Prompt có số phiên bản; lưu nguyên kết quả thô vào `extraction_runs`.
5. **Validate.** Chạy các kiểm tra tự động dưới đây. Trượt bất kỳ kiểm tra nào thì bảng vào `review_queue` kèm lý do.
6. **Publish.** Bảng qua hết kiểm tra chuyển sang published, bảng cũ cùng loại chuyển sang superseded, tính lại `district_summary`, xóa cache các trang liên quan.

Các kiểm tra của bước Validate:

- Lương không giảm khi tăng bậc trong cùng một lane, và không giảm khi sang lane cao hơn ở cùng một bậc. Ngoại lệ phải có ghi chú.
- Số ô bằng số bậc nhân số lane, trừ các ô trống có đánh dấu.
- Giá trị nằm trong khoảng hợp lý cho lương năm, không lẫn lương theo giờ hay theo ngày.
- Năm học đọc được và không cũ hơn bảng đang published.
- Trích hai lần độc lập rồi so khớp từng ô; lệch thì chuyển xem tay.
- Lương khởi điểm đổi quá 20% so với năm trước của cùng học khu thì chuyển xem tay.

Vận hành pipeline:

- Chạy theo lô bằng GitHub Actions, chia theo bang, có điểm lưu để chạy tiếp từ chỗ dừng.
- Thứ tự phủ: học khu đông học sinh nhất trước.
- Chạy thử 100 học khu trước. Báo cáo: tỉ lệ tìm thấy tài liệu, tỉ lệ qua Validate, chi phí trung bình mỗi học khu, các kiểu lỗi. Chỉ mở rộng khi chủ dự án duyệt chi phí.
- Dựng trang xem tay nội bộ có bảo vệ: PDF gốc đặt cạnh bảng đã trích, có nút duyệt, sửa, loại.
- Học khu không có bảng lương công khai vẫn có trang, ghi rõ "schedule not found", kèm link website và đặt noindex.

Nghiệm thu (ngưỡng là đề xuất của tôi, chủ dự án có thể đổi):

- Lập bộ chuẩn gồm 30 bảng lương nhập tay. Với các bảng được publish, từ 99% số ô khớp bộ chuẩn.
- Không bảng sai nào trong bộ chuẩn lọt qua Validate.
- Chạy lại pipeline trên cùng dữ liệu không tạo bản ghi trùng.

## Công đoạn 6: website

Mọi trang được render phía server từ D1 và cache ở edge; mỗi bang và mỗi học khu có URL riêng để Google index được.

| URL | Nội dung |
| --- | --- |
| `/` | Ô tìm học khu, danh sách bang, giải thích ngắn cách đọc bảng lương |
| `/{state}` | Danh sách học khu của bang, sắp xếp được theo lương khởi điểm và lương tối đa |
| `/{state}/{district}` | Bảng lương năm mới nhất, máy tính, học khu lân cận, lịch sử, nguồn |
| `/{state}/{district}/{school-year}` | Bảng lương của một năm cũ |
| `/compare?d=a,b,c` | So sánh tối đa 4 học khu ở cùng bậc và lane |
| `/calculator` | Máy tính độc lập: chọn học khu, bằng cấp, số năm kinh nghiệm |
| `/search?q=` | Tìm theo tên học khu, thành phố, quận |
| `/about`, `/methodology`, `/privacy`, `/terms`, `/contact` | Trang tin cậy và pháp lý |
| `/sitemap.xml`, `/robots.txt` | Sitemap chỉ chứa trang có bảng published |

Trang học khu gồm các phần theo thứ tự:

1. Tiêu đề dạng "{District} Teacher Salary Schedule {school year}".
2. Dòng tóm tắt: lương khởi điểm, lương tối đa, số ngày hợp đồng.
3. Bảng lương đầy đủ bằng thẻ table HTML thật, cuộn ngang trên điện thoại, cột bậc đứng yên.
4. Máy tính: chọn lane và số năm, ra lương năm, lương theo ngày, mức tăng mỗi bậc.
5. So sánh với 5 đến 10 học khu lân cận ở ba mốc: BA bậc 1, MA bậc 10, mức tối đa.
6. Phụ cấp và ghi chú, giữ nguyên văn.
7. Nguồn: link tài liệu gốc, số trang, ngày tải, trạng thái kiểm tra, nút "Report an error".
8. Link tới các năm trước.

Yêu cầu kỹ thuật:

- HTML render trong Worker. JavaScript phía client chỉ dùng cho máy tính và sắp xếp bảng.
- Cache HTML ở edge; khi publish thì xóa cache của học khu đó, bang đó và các học khu lân cận.
- Thiết kế cho điện thoại trước. Chừa sẵn khung quảng cáo có kích thước cố định để bố cục không xô lệch.
- Khả năng tiếp cận: ô tiêu đề có `scope`, độ tương phản đạt, dùng được bằng bàn phím.
- Form báo lỗi ghi vào D1 và có chống spam (Cloudflare Turnstile).

Nghiệm thu:

- 20 trang học khu California ngẫu nhiên hiển thị đúng với nguồn.
- Tắt JavaScript vẫn đọc được toàn bộ bảng lương.
- Lighthouse mobile performance từ 90 trở lên khi chưa gắn quảng cáo.
- Sitemap chỉ gồm trang có bảng published.

## Công đoạn 7: SEO

Trang chỉ được index khi có dữ liệu đã kiểm tra và có ít nhất một thứ PDF gốc không có. Đây là ranh giới giữa công cụ tra cứu và nội dung sinh hàng loạt, thứ Google đã phạt nặng trong các đợt cập nhật năm 2026.

- Quy tắc index: trang có bảng published và có phần so sánh lân cận thì cho index. Mọi trang khác đặt noindex.
- Mở index theo đợt, từng bang một. Xem Search Console trước khi mở đợt sau.
- Title, H1 và meta description sinh từ dữ liệu thật: tên học khu, năm học, khoảng lương. Không nhồi từ khóa.
- Câu mô tả trên trang sinh từ số liệu, ví dụ chênh lệch với trung vị của bang. Không dùng đoạn văn chung chung lặp lại giữa các trang.
- Structured data: `Dataset` cho trang học khu và `BreadcrumbList` cho điều hướng.
- Liên kết nội bộ: bang, học khu, học khu lân cận và trang so sánh trỏ qua lại.
- Trang năm cũ có canonical riêng; trang học khu luôn hiện năm mới nhất.
- Trang `/methodology` giải thích nguồn, cách trích, cách kiểm tra và tỉ lệ lỗi đã biết.
- Mở rộng sau khi có dữ liệu thật: lương giáo viên dạy thay, bảng lương nhân viên trường, trang so sánh hai học khu cụ thể.
- Theo dõi: Google Search Console, Bing Webmaster Tools, log 404, trang không có link trỏ tới.

Nghiệm thu:

- Không trang noindex nào nằm trong sitemap.
- Công cụ Rich Results Test không báo lỗi trên trang học khu.
- Không có hai trang trùng title.

## Công đoạn 8: quảng cáo và pháp lý

Bắt đầu bằng Google AdSense và chuyển sang mạng quảng cáo có quản lý khi đủ traffic; các trang pháp lý phải xong trước khi nộp đơn.

- Trước khi nộp AdSense, site cần có: about, methodology, privacy, terms, contact, và đủ trang có dữ liệu thật.
- Đặt file `ads.txt` ở gốc tên miền.
- Vị trí quảng cáo: dưới dòng tóm tắt, giữa bảng lương và phần so sánh, cuối trang. Không chèn vào giữa bảng lương, không che máy tính.
- Khung quảng cáo có chiều cao đặt trước. Quảng cáo dưới màn hình đầu thì tải lười.
- Đồng ý cookie: Claude kiểm tra yêu cầu hiện hành của AdSense về nền tảng quản lý đồng ý cho khách từ châu Âu và về luật quyền riêng tư của các bang Mỹ, rồi mới tích hợp.
- Ngưỡng nâng cấp tham khảo, theo các bài tổng hợp năm 2026: Raptive khoảng 25.000 lượt xem mỗi tháng, Mediavine khoảng 50.000 phiên mỗi tháng. Kiểm tra lại trên trang chính thức của từng mạng.
- Miễn trừ hiện ở chân mọi trang: số liệu chỉ để tham khảo, trích tự động từ tài liệu công khai; lương thực tế do học khu quyết định; site không liên kết với học khu hay cơ quan nhà nước nào.
- Có quy trình gỡ hoặc sửa khi học khu yêu cầu, qua trang contact.
- Đo lường bằng công cụ ít xâm phạm riêng tư, ví dụ Cloudflare Web Analytics.

Nghiệm thu:

- `ads.txt` truy cập được từ trình duyệt.
- Gắn quảng cáo xong, chỉ số xô lệch bố cục (CLS) vẫn trong ngưỡng tốt.
- Trang privacy nêu rõ cookie quảng cáo và cách từ chối.

## Công đoạn 9: vận hành và cập nhật

Bảng lương đổi theo từng năm học, nên việc chính sau khi ra mắt là phát hiện tài liệu mới và chạy lại pipeline tự động.

- Lịch GitHub Actions kiểm tra lại URL nguồn của mỗi học khu theo định kỳ, dày hơn vào mùa hè. File có sha256 đổi thì chạy lại từ bước Classify.
- Chạy lại Discover cho học khu chưa có bảng, hoặc có bảng cũ hơn một năm học.
- Nhập lại dữ liệu bang khi California và Kentucky công bố năm mới.
- Bảng theo dõi nội bộ: số bảng published theo bang, tỉ lệ thất bại của từng bước, chi phí LLM theo ngày, link nguồn chết, báo lỗi của người dùng chưa xử lý.
- Cảnh báo khi: chi phí vượt ngân sách ngày, tỉ lệ qua Validate tụt, Worker trả lỗi 5xx tăng, sắp chạm giới hạn của D1 hoặc Workers.
- Sao lưu D1 ra R2 theo định kỳ và thử khôi phục.
- Trang công khai về độ phủ dữ liệu: số học khu đã có bảng theo bang, ngày cập nhật gần nhất.
- Nhật ký thay đổi: mỗi lần sửa bảng đã published thì lưu giá trị trước, giá trị sau và lý do.

Nghiệm thu:

- Giả lập một PDF đổi nội dung: bảng mới được published và bảng cũ thành superseded mà không cần thao tác tay.
- Khôi phục D1 từ bản sao lưu thành công trên database preview.

## Công đoạn 10: mở rộng sang bảng lương khu vực công

Sau khi mảng giáo viên chạy ổn, cùng pipeline và cùng website mở sang cảnh sát, cứu hỏa, y tá, nhân viên thành phố và nhân viên bang. Đây là phần có nhu cầu tra cứu lớn nhất và là đường chính để đạt mục tiêu doanh thu.

Căn cứ nhu cầu, theo ước tính của Semrush: [federalpay.org](https://tr.semrush.com/website/federalpay.org/overview) chỉ phủ bảng lương liên bang mà đạt 0,73 đến 1,06 triệu lượt truy cập mỗi tháng đầu năm 2025. [govsalaries.com](https://cw.semrush.com/website/govsalaries.com/overview) đạt khoảng 1,06 triệu lượt trong tháng 8/2025. Bảng lương của bang, thành phố, cảnh sát, cứu hỏa và y tá vẫn nằm rải rác trong PDF.

Điều kiện để bắt đầu:

- Mảng giáo viên đạt ngưỡng nghiệm thu của Công đoạn 5 khi chạy trên diện rộng.
- Đã có số đo chi phí trích xuất cho mỗi tài liệu.
- Trang giáo viên được Google index ổn định, không bị loại hàng loạt.

Thứ tự mở rộng, từ dễ đến khó:

| Thứ tự | Nhóm | Nguồn tài liệu | Khác với bảng lương giáo viên |
| --- | --- | --- | --- |
| 1 | Giáo viên dạy thay và nhân viên trường | Cùng website học khu đã thu thập | Lương theo ngày hoặc theo giờ |
| 2 | Cảnh sát và cứu hỏa | Bảng lương và thỏa ước lao động trên website thành phố, quận | Lương theo giờ hoặc tháng; chỉ có bậc, không có lane; nhiều phụ cấp |
| 3 | Nhân viên thành phố và quận | Bảng lương chung của thành phố | Hàng trăm chức danh, mỗi chức danh một dải bậc |
| 4 | Nhân viên bang | Pay plan do bang công bố | Ma trận ngạch × bậc |
| 5 | Y tá | Hợp đồng công đoàn, bệnh viện công | Lương theo giờ; chỉ có ở nơi có công đoàn |

Không làm bảng lương liên bang, vì federalpay.org đã phủ mảng này.

Thay đổi về dữ liệu:

1. Đổi tên bảng `districts` thành `employers` bằng một migration. Cột `employer_type` nhận các giá trị school\_district, city, county, state, hospital.
2. Nhập danh mục thành phố và quận từ dữ liệu của Census Bureau. Claude tìm đúng file và ghi URL vào `DECISIONS.md`.
3. `schedule_type` nhận thêm các giá trị police\_officer, firefighter, registered\_nurse, general\_employee.
4. Dùng `pay_basis` và `hours_per_year` để quy đổi giữa lương giờ, tháng và năm. Luôn hiện số gốc trong tài liệu; số quy đổi phải ghi rõ là quy đổi.
5. Thêm bảng `classifications` cho bảng lương nhiều chức danh: mỗi dòng là một chức danh kèm ngạch, các bậc là cột.
6. Bước Validate dùng khoảng hợp lý riêng cho từng `pay_basis` và từng nhóm nghề.
7. Prompt trích xuất có phiên bản riêng cho từng nhóm nghề; không sửa prompt giáo viên đang chạy.

Thay đổi về website:

- URL `/{state}/{employer}` giữ nguyên cho học khu. Nghề khác dùng `/{state}/{employer}/{occupation}`.
- Slug thành phố và quận có hậu tố loại đơn vị để không trùng với học khu cùng tên.
- Thêm trang nghề theo bang, ví dụ `/{state}/police-officer-salary`, liệt kê và so sánh mọi đơn vị trong bang.
- Phần so sánh lân cận chỉ so các đơn vị cùng nghề.
- Máy tính có thêm quy đổi giờ, tháng, năm.
- Tên miền và tên site không nên gắn chữ "teacher", để dùng được cho mọi nghề. Cân nhắc điểm này khi chốt tên miền.

Nguyên tắc không đổi:

- Chỉ đăng bảng lương, không đăng tên và lương của từng cá nhân.
- Mỗi nhóm nghề mở index theo đợt, theo quy tắc của Công đoạn 7.
- Mỗi nhóm nghề chạy thử trên mẫu nhỏ và báo cáo chi phí trước khi mở rộng.

Nghiệm thu:

- Sau migration, mọi trang giáo viên giữ nguyên URL và dữ liệu.
- Chạy thử cảnh sát ở 50 thành phố đông dân nhất: có báo cáo tỉ lệ tìm thấy tài liệu, tỉ lệ qua Validate và chi phí.
- Mỗi nhóm nghề có bộ chuẩn 20 bảng nhập tay; với các bảng được publish, từ 99% số ô khớp bộ chuẩn.

## Rủi ro và quyết định còn mở

Năm quyết định dưới đây cần bạn chốt; Claude không tự quyết các điểm này.

- [ ] Tên miền và tên tiếng Anh của site. Đã chốt hướng: làm sau, không chứa "teacher" (D-002).
- [x] Giữ stack của travienphi hay chuyển hẳn sang Workers + D1. Đã chốt 2026-11-12: Workers Paid, chung tài khoản; pipeline Python (D-001, D-003, D-004).
- [ ] Model và nhà cung cấp LLM cho bước Extract.
- [ ] Ngân sách tối đa cho API trích xuất. Chốt sau khi có số đo từ 100 học khu chạy thử.
- [ ] Có đưa trường bán công (charter school) vào hay không.

| Rủi ro | Dấu hiệu nhận biết | Cách giảm |
| --- | --- | --- |
| Số liệu lương sai | Báo lỗi từ người dùng, lệch khi kiểm tra chéo | Trích hai lần, bước Validate, link gốc, nhãn trạng thái |
| Google coi là nội dung hàng loạt | Trang không được index, traffic tụt sau một đợt cập nhật | Chỉ index trang đã kiểm tra và có so sánh; mở theo đợt |
| Người tìm bấm thẳng vào PDF của học khu | Tỉ lệ bấm thấp với truy vấn tên học khu | Nhắm truy vấn so sánh, máy tính, lương dạy thay |
| Đối thủ mở rộng nhanh | [CreditsForTeachers](https://creditsforteachers.com/texas-teacher-salary-by-district/) thêm học khu mỗi tuần | Phủ rộng hơn, sâu hơn cho từng học khu, giữ lịch sử nhiều năm |
| Chi phí trích xuất cao | Chi phí mỗi học khu vượt dự kiến ở lần chạy thử | Chỉ gửi đúng trang có bảng, bỏ qua file không đổi, dùng dữ liệu bang trước |
| Traffic theo mùa | Lượt xem dồn vào mùa tuyển dụng | Nội dung dùng quanh năm: so sánh bang, lịch sử tăng lương |
| Doanh thu không đạt 3.000 USD mỗi tháng | RPM hoặc traffic thấp sau khi ra mắt | Đo thật rồi mới quyết mở rộng; chưa có số liệu RPM riêng cho ngách này |

Nguồn đã tra ngày 12/11/2026, qua kết quả tìm kiếm: [CDE J-90](https://cde.ca.gov/ds/fd/cs/), [CDE C-90](https://www.cde.ca.gov/FG/sf/c90.asp), [Kentucky Department of Education](https://www.education.ky.gov/districts/FinRept/Pages/School%20District%20Personnel%20Information.aspx), [NCTQ Teacher Contract Database](https://nctq.org/districtPolicy). Tôi chưa mở từng file dữ liệu, nên định dạng cụ thể cần Claude xác nhận khi làm Công đoạn 4.
