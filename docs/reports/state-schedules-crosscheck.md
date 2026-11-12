# Kiểm tra chéo bảng lương của bang với tài liệu của học khu (Công đoạn 4)

Ngày 12/11/2026. So bảng đã nhập (CA J-90, KY KDE) với bảng lương do chính học khu công bố.

## Cách làm

- Tìm tài liệu bằng tìm kiếm web, kê khai URL trong `pipeline/sources/crosscheck-state-2425.json`,
  tải bằng workflow Fetch sources (tuân thủ robots.txt), lưu ở các Release `src-crosscheck-state-2425-*`.
  Tệp cuối cùng dùng để so: Release `src-crosscheck-state-2425-20261112-43212795973` (và
  `…-43212322656`, `…-43211820288` cho các tệp tải ở đợt trước).
- Đọc PDF bằng `pdftotext -layout`, so **từng ô** bằng script: mỗi bậc (hoặc số năm kinh nghiệm),
  tập số tiền trong PDF phải trùng tập số tiền của bậc đó trong D1. KY so theo từng Rank.
- Mẫu ngẫu nhiên 10 học khu/bang trong báo cáo nhập hầu hết là học khu nhỏ không đăng bảng lương
  công khai, hoặc chặn tải tự động (403, robots.txt, trang Wix/thrillshare). Trong mẫu ngẫu nhiên chỉ
  tìm được tài liệu của Lake Tahoe, Red Bluff (CA) và Anderson, Henry (KY); phần còn lại lấy các học
  khu có tài liệu tải được.

## California (J-90)

| Học khu | Tài liệu học khu | Năm so | Kết quả | Xử lý |
|---|---|---|---|---|
| Irvine Unified | [Certificated Salary Schedule 2024-2025](https://iusd.org/sites/default/files/documents/2425-CERTSAL_CE.pdf) | 2024-25 | **Khớp 135/135 ô** | – |
| Red Bluff Joint Union High | [CTA agreement, Appendix A 2023/24](https://www.rbhsd.org/documents/Departments/Human-Resources/Bargaining-Agreements/CTA-Bargaining-Agreement-rev.-2023-10-21.pdf) | 2023-24 | **Khớp 62/62 ô**, 31 bậc. Bảng 189 ngày (Salisbury) không có trong J-90. J-90 2024-25 trùng hệt 2023-24. | – |
| Lake Tahoe Unified | [STEA salary schedule 2023-24](https://www.ltusd.org//Userfiles/DBFiles/server_2738240/202308/51031672/g_stea_salary_schedule.pdf) (đọc qua WebFetch; khi tải tự động thì 404) | 2023-24 | Khớp phần đọc được: cả hàng bậc 1 (6 cột), ô lớn nhất $126,894, 183 ngày | – |
| Placentia-Yorba Linda Unified | [Certificated Salary Schedule 2024-2025](https://aple.org/wp-content/uploads/2024/01/Certificated-Sal-Schedule-24-25-2.pdf) | 2024-25 | **Lệch 1 ô**: bậc 6 cột V, học khu $87,267, J-90 $87,627 (đảo chữ số). 44/45 ô khớp. Validate không bắt được vì vẫn tăng dần. | Giữ xem tay (`pipeline/review-holds.json`) |
| Pittsburg Unified | [Certificated 2024-2025, 1.07%](https://pittsburgusd.net/documents/Departments/Human-Resources/Human-Resources-Home/2024-2025%20salary%20increase%201%20percent/2024-2025-Certificated-1.07-effective-July-1-2024-Final.pdf) | 2024-25 | **Lệch 1 ô**: bậc 4 cột VI, học khu $76,781, J-90 $76,006 (chép nhầm số cột V). 86/87 ô khớp. | Giữ xem tay |
| Elk Grove Unified | [EGEA #10 2024-2025](https://www.egusd.net/documents/Employment/Quick-Links/Salary-Schedules/2024-25-EGEA-10-and-17.pdf) (duyệt 25/6/2024) | 2024-25 | **Lệch toàn bảng**: PDF trùng J-90 2023-24; J-90 2024-25 cao hơn đều $2,550 mỗi ô. Có thể học khu điều chỉnh sau khi đăng PDF. Tài liệu học khu cũ hơn J-90 nên không thay. | Giữ xem tay đến khi có bảng mới hơn |
| Salinas City Elementary | [Certificated Salary Schedules 2024-25](https://resources.finalsite.net/images/v1736383845/salinascityesdorg/shuphwczaomg7ua6njw1/24-25CertificatedSalarySchedules.pdf) | 2024-25 | 19/23 bậc khớp. 4 bậc lệch do J-90 nhập sai ô (cột BA+15 bậc 6, cột BA+60 bậc 6-8 lệch dòng). | **Validate đã giữ lại** (lương giảm khi sang lane) |
| Fresno Unified | [Teacher Salary Schedules 2024/2025](https://resources.finalsite.net/images/v1721246054/fresnouorg/t7o9hdb3ykj8u00zemjb/TeacherLibrariansSalarySchedulesEffectiveJuly12024.pdf) | 2024-25 | J-90 gộp 4 bảng (185 ngày, nurse, 195 ngày, 200-218 ngày) vào một lưới 20 cột và xếp bậc khác tài liệu; không so được từng ô. Hàng đầu (Non-credentialed $59,054, Class I $65,641) khớp. | **Validate đã giữ lại** |
| Rialto Unified | [194-day salary schedule 2024/25](https://kec.rialto.k12.ca.us/cms/lib/CA50000591/Centricity/Domain/1398/TEACHERS_194dys__24_25.pdf) | 2024-25 | J-90 là bảng 184 ngày, tài liệu tải được là bảng 194 ngày. Quy đổi theo số ngày, 36/44 ô lệch ≤ $2, mọi ô ≤ $5. Chưa kết luận. | – |
| Chatom Union | [Certificated Annual Salary Schedule 2024-25](https://chatom.k12.ca.us/wp-content/uploads/2025/06/2024-25-Certificated-Salary-Schedule-Final.pdf) | 2024-25 | Không nộp J-90 2024-25. Học khu có bảng công khai: ứng viên cho pipeline PDF. | – |

## Kentucky (KDE)

Các học khu dưới đây đều đăng bảng theo Rank I/II/III (+ IV, V một mức). So cột cơ bản x1.

| Học khu | Tài liệu học khu | Năm so | Kết quả |
|---|---|---|---|
| Anderson County | [Approved Salary Schedules 2024-2025](https://www.anderson.kyschools.us/Downloads/Approved%20Salary%20Schedules%20for%202024-2025.pdf) | 2024-25 | **Khớp 99/99 ô** (Rank I-III, 0-32 năm). Cột "Doctorate" của học khu là bảng tùy chọn, không có trong cột x1 của KDE. |
| Henry County | [Certified Salary Schedule 2025-2026](https://resources.finalsite.net/images/v1745335293/henrykyschoolsus/qvel6e2vmp9jxxlfbduh/FY2026187CERTIFIEDSALARY.pdf) | 2025-26 | **Khớp 96/96 ô**, Rank IV/V cũng khớp |
| Fort Thomas Independent | [Certified Salary Schedule 2025-2026](https://files-backend.assets.thrillshare.com/documents/asset/uploaded_file/5483/Ftis/dadabab3-c8bd-4352-8c9e-44649708266f/2025-26_Salary_Schedules_Combined.pdf?disposition=inline) | 2025-26 | **Khớp 120/120 ô** (Rank IV, III, II, I). Rank IIIA, IIA của học khu là mã x2 của KDE, không nhập (D-017). |
| Henderson County | [Salary Schedules 2025-2026](https://core-docs.s3.us-east-1.amazonaws.com/documents/asset/uploaded_file/3112/HCS/5809284/2025-26_Salary_Schedules.pdf) | 2025-26 | **Khớp 84/84 ô** |
| Bullitt County | [2025-2026 Annual Pay Scales](https://portal.ksba.org/public/Meeting/Attachments/DisplayAttachment.aspx?AttachmentID=883311) | 2025-26 | **Khớp 84/84 ô**. Học khu ghi mã 31/32/21/22/11, xác nhận cột x2 là "+15 giờ" (3A, 2A). |
| McLean County | [Salary Schedules 2025-2026](https://files-backend.assets.thrillshare.com/documents/asset/uploaded_file/5659/Mcsd/98c46af5-4582-4b57-9358-59022753f043/2025-2026-Salary-Schedule-(1).pdf?disposition=inline) | 2025-26 | **Khớp 93/93 ô** |
| Pulaski County | [2025-2026 Salary Schedules](https://resources.finalsite.net/images/v1749648865/pulaskinet/zzebfwjkw8da274g3z2m/2025-2026SalarySchedule.pdf) | 2025-26 | **Khớp 112/112 ô** (Rank 4, 3, 2, 1) |

Thêm, không tính vào số trên: tin tuyển dụng của Spencer County (năm 2026-27) ghi khoảng lương
$45,953-$78,131, trùng ô Rank III 0 năm và ô lớn nhất của bảng 2025-26 đã nhập.

## Tổng hợp

- **KY: 7 học khu, 688/688 ô khớp.** Chưa đủ 10: các học khu còn lại tìm được tài liệu đều chặn tải
  tự động (403) hoặc chỉ có bảng 2026-27. Dữ liệu KDE do chính học khu nộp, và cả 7 lần so đều khớp
  tuyệt đối.
- **CA: 10 học khu.** 3 khớp hoàn toàn (Irvine, Red Bluff, Lake Tahoe phần đọc được); 2 lệch một ô do
  J-90 nhập sai (Placentia-Yorba Linda, Pittsburg); 1 lệch toàn bảng do khác thời điểm (Elk Grove);
  2 sai cấu trúc đã bị Validate giữ lại (Salinas City, Fresno); 1 chưa kết luận (Rialto); 1 không có
  trong J-90 (Chatom).
- Bài học cho Công đoạn 5:
  - J-90 có lỗi nhập tay mà kiểm tra tăng dần không bắt được (đảo chữ số, chép nhầm cột). Bảng J-90
    nên được đối chiếu với tài liệu học khu khi pipeline PDF tìm thấy tài liệu, và tài liệu học khu
    mới hơn được ưu tiên (PLAN).
  - Khoảng 19% học khu CA và 18% học khu KY có bảng năm sau trùng hệt năm trước (chưa tăng lương hoặc
    hợp đồng chưa chốt khi nộp). Không phải lỗi, nhưng trang học khu nên ghi rõ ngày hiệu lực.
  - Học khu CA có nhiều bảng theo số ngày làm việc (184/194 ngày…); J-90 chỉ giữ một bảng.
