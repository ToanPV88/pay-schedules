# Nguồn bảng lương giáo viên tập trung theo bang

PLAN Công đoạn 4 yêu cầu tìm thêm bang có dữ liệu bảng lương tập trung (một nơi công bố bảng lương của
nhiều học khu), để nhập trước pipeline PDF. Tra ngày 12/11/2026 bằng tìm kiếm web. Chưa tải hay đọc
từng tệp, trừ CA và KY đã nhập.

Phân loại:

- **A. Bảng lương đầy đủ, dạng máy đọc được** (Excel, CSDL): nhập như CA, KY.
- **B. Bảng lương đầy đủ trong PDF tập trung**: một tệp hoặc một thư mục do cơ quan bang công bố, có
  bảng bậc × lane của từng học khu. Cần trích bảng từ PDF (pipeline Công đoạn 5), nhưng khỏi bước
  Discover.
- **C. Kho hợp đồng lao động tập thể (CBA)**: cơ quan quan hệ lao động của bang lưu hợp đồng của các
  học khu; bảng lương nằm trong phụ lục. Dùng làm nguồn Discover cho pipeline PDF.
- **D. Chỉ số tóm tắt** (lương khởi điểm, cao nhất, trung bình): không đủ để dựng bảng, dùng để đối
  chiếu hoặc kiểm tra hợp lý.
- **E. Không thấy nguồn tập trung**, hoặc bang chỉ có bảng lương tối thiểu của bang.

Dữ liệu lương **từng người** (vd. Illinois Teacher Service Record, Pennsylvania Professional Personnel,
Washington S-275, các trang "transparency") bị loại theo nguyên tắc 3 của PLAN, không ghi ở đây.

## Đã nhập

| Bang | Nguồn | Loại | Ghi chú |
|---|---|---|---|
| CA | [CDE Certificated Salaries & Benefits (J-90)](https://cde.ca.gov/ds/fd/cs/) | A | Access trong ZIP tự giải nén; khảo sát tự nguyện (~83% LEA). Từ 2025-26 chuyển sang [C-90](https://www.cde.ca.gov/FG/sf/c90.asp). D-016, D-017. |
| KY | [KDE School District Personnel Information](https://www.education.ky.gov/districts/FinRept/Pages/School%20District%20Personnel%20Information.aspx) | A | Excel 2014-2026, đủ 171 học khu. D-016, D-017. |

## Ứng viên nên làm tiếp (theo thứ tự đề xuất)

| Bang | Nguồn | Loại | Học khu | Việc cần làm |
|---|---|---|---:|---|
| MD | [MSDE Professional Salary Schedules](https://www.marylandpublicschools.org/about/Pages/DCAA/SSP/index_SSP-Staff.aspx), vd. [2025-26](https://marylandpublicschools.org/about/Documents/DCAA/SSP/20252026Staff/2026-professional-salary-schedules-a.pdf), [2024-25](https://www.marylandpublicschools.org/about/Documents/DCAA/SSP/20242025Staff/2024-2025-Professional-Salary-Schedules-A.pdf) | B | 24 | Một PDF mỗi năm gồm bảng lương của cả 24 hệ thống trường, có từ 2012. Ít học khu, học khu lớn: nên làm đầu tiên. |
| WV | [WVDE School Finance Data](https://wvde.us/about-us/finance/school-finance/school-finance-data/2025-2026): [Professional Salary Schedules by County 2025-26](https://wvde.us/sites/default/files/2025-07/Professional%20Salary%20Schedules%20by%20County%2026.pdf) | B | 55 | Bảng lương bang + phụ cấp từng quận, một PDF. |
| AR | [DESE Salary Reports](https://dese.ade.arkansas.gov/Offices/fiscal-and-administrative-services/publication-and-reports/salary-reports) | B? | ~230 | Luật Arkansas buộc học khu đăng bảng lương; trang DESE có báo cáo lương. Cần mở xem có bảng từng học khu hay chỉ tóm tắt. |
| IN | [IEERB](https://secure.in.gov/ieerb/education-employment-research/overview): CBR qua [Gateway](https://gateway.iFionline.org/guides/about/LearnMoreCBR.pdf), [Teacher Compensation Report](https://in.gov/ieerb/files/2023-24-Teacher-Compensation-Report.pdf) | C + D | ~290 | Học khu nộp hợp đồng và dữ liệu lương lên IEERB hằng năm. Cần xem Gateway có xuất bảng lương có cấu trúc không. |
| OH | [SERB](https://serb.ohio.gov) kho hợp đồng, vd. [hợp đồng PDF](https://dam.assets.ohio.gov/image/upload/serb.ohio.gov/PDF/Contracts/2024/24-MED-01-0081.pdf), [Wage Settlement 2025](https://dam.assets.ohio.gov/image/upload/serb.ohio.gov/PDF/Wage_Settlement/Wage_Settlement_2025.pdf) | C + D | ~600 | Mọi CBA khu vực công nộp cho SERB. Cần cách liệt kê hợp đồng theo học khu. |
| NY | [PERB Collective Bargaining Agreements](https://perb.ny.gov/collective-bargaining-agreements) | C | ~680 | Kho hợp đồng của PERB (Cornell lưu trữ bản cũ). |
| AK | [Salary and Benefits Schedule for School Districts](https://doa.alaska.gov/dop/HB278SchoolStudy/) (Sở Hành chính Alaska, theo HB 278) | B? | 53 | Nghiên cứu theo luật, có phụ lục bảng lương từng học khu; cần xem năm mới nhất. |
| NH | [NH DOE Staffing and Salary Reports](https://education.nh.gov/who-we-are/division-of-educator-and-analytic-resources/bureau-of-education-statistics/staffing-and-salary-reports), vd. [teach-sal-schedl23-24.pdf](https://www.education.nh.gov/sites/g/files/ehbemt326/files/inline-documents/sonh/teach-sal-schedl23-24.pdf) | D (có thể B) | ~170 | Tên tệp gợi ý bảng lương theo học khu; cần mở xem là bảng đủ hay chỉ min/max. |
| WA | [Báo cáo CBA K-12 của LEAP/OFM](https://fiscal.wa.gov/K12/K12CollectiveBargainingAgreementReport.pdf) (RCW 43.88.583) | C/D | ~295 | Học khu nộp CBA cho bang theo luật; cần xem có kho hợp đồng công khai không. |
| TN | [SBE: LEA Alternative Salary Schedules](https://tn.gov/content/dam/tn/stateboardofeducation/documents/2024-sbe-meetings/may-31%2c-2024-/5-31-24%20VI%20P%20LEA%20Alternative%20Salary%20Schedules%20Cover.pdf), [TN Firefly Teacher Pay](https://tnfirefly.com/data/teacher-salaries) | B? / D | ~145 | SBE duyệt bảng lương thay thế của từng LEA; Firefly là cổng dữ liệu minh bạch của bang. Cần kiểm. |

## Nguồn ngoài cơ quan bang (dùng cho Discover, không phải dữ liệu tập trung chính thức)

| Phạm vi | Nguồn | Ghi chú |
|---|---|---|
| ~150 học khu lớn nhất cả nước | [NCTQ Teacher Contract Database](https://nctq.org/districtPolicy) | Bản sao bảng lương và hợp đồng do học khu ban hành. Dùng để Discover và đối chiếu. |
| CT | [ConnCAN Teacher Contracts](https://teachercontracts.conncan.org) | Tổ chức phi lợi nhuận, kho hợp đồng giáo viên CT; cần xem còn cập nhật không. |
| MO | [MSTA salary book](https://msta.org/hubfs/salary-book-2024-25-web.pdf.pdf?hsLang=en), [MNEA salary rankings](https://www.mnea.org/sites/default/files/publications/SalaryResearch/Salary%20Rankings_2025.pdf) | Hiệp hội giáo viên; chủ yếu chỉ số tóm tắt (D). |
| NY | [SeeThroughNY contracts](https://www.empirecenter.org/publications/seethroughny-updated-with-latest-union-contracts-2/) | Empire Center; kho hợp đồng khu vực công. |

## Chưa thấy nguồn tập trung (E) hoặc chỉ có bảng tối thiểu của bang

- Bảng tối thiểu hoặc bảng của bang cộng phụ cấp địa phương, không có bảng từng học khu ở một nơi:
  NC ([DPI salary schedules](https://www.dpi.nc.gov/fbs/finance/salary)), GA, SC (bang công bố bảng tối
  thiểu; bảng từng học khu nằm trên site học khu), MS, AL, TN (bảng tối thiểu), NM (mức tối thiểu theo
  bậc chứng chỉ), DE, ID, LA (luật R.S. 17:418 buộc học khu có bảng lương; LDOE có lưu một số
  [chính sách lương](https://metastorm.doe.louisiana.gov/attachments/NEWS-000001384/Avoyelles%20Salary%20Policy.pdf)
  nhưng chưa thấy trang tổng hợp).
- Chưa thấy nguồn tập trung, cần pipeline PDF theo học khu: AZ, CO, CT, FL (FLDOE có báo cáo lương
  trung bình, chưa thấy bảng từng học khu), IA, IL (chỉ có dữ liệu cá nhân, loại), KS, MA (DESE chỉ có
  lương trung bình), ME, MI, MN, MO, MT, NE, NJ, NV, ND, OK, OR, PA (chỉ có dữ liệu cá nhân, loại), RI,
  SD, TX (TEA chỉ có bảng tối thiểu), UT, VA (VDOE có khảo sát lương trung bình), VT, WI, WY.
- Một học khu cả bang: HI (Hawaii DOE), DC (DCPS). Nhập tay một bảng là đủ.

Những dòng "cần kiểm" và "chưa thấy" dựa trên tìm kiếm, chưa mở từng trang; nên xem lại trước khi
bỏ qua một bang ở Công đoạn 5.
