# Báo cáo nhập bảng lương của bang, CA J-90 và KY (Công đoạn 4)

Sinh bởi `pay-pipeline schedules-build` (cùng lệnh workflow Import schedules chạy), nguồn Release
`src-state-salaries-2425-20261112-43205697035`, danh mục D1 ngày 12/11/2026, có áp `pipeline/review-holds.json`.
Kiểm tra chéo: [state-schedules-crosscheck.md](state-schedules-crosscheck.md). Quyết định: D-016…D-018.


## Tệp nguồn

| Tệp | URL | SHA-256 | Tải lúc | Release |
|---|---|---|---|---|
| j902324.exe | https://www3.cde.ca.gov/ds-downloads/fd/cs/j902324.exe | `c7eb835b4da4…` | 2026-11-12T11:03:22Z | src-state-salaries-2425-20261112-43205697035 |
| j902425.exe | https://www3.cde.ca.gov/ds-downloads/fd/cs/j902425.exe | `60b9b85b97ea…` | 2026-11-12T11:03:16Z | src-state-salaries-2425-20261112-43205697035 |
| ky_certified_salary_schedule_2014-2026.xlsx | https://www.education.ky.gov/districts/FinRept/Documents/Certified%20Salary%20Schedule%20%282014-2026%29.xlsx | `e0c899f593ed…` | 2026-11-12T11:03:31Z | src-state-salaries-2425-20261112-43205697035 |

## Kết quả theo bang và năm học

| Bang | Năm học | Học khu trong tệp | Nhập được | Tỉ lệ | Bỏ qua | Bảng ghi vào D1 | Published | Chờ xem tay |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CA | 2023-24 | 845 | 839 | 99.3% | 6 | 844 | 761 | 83 |
| CA | 2024-25 | 828 | 824 | 99.5% | 4 | 829 | 736 | 93 |
| KY | 2024-25 | 171 | 171 | 100.0% | 0 | 171 | 155 | 16 |
| KY | 2025-26 | 171 | 171 | 100.0% | 0 | 171 | 161 | 10 |

Học khu trong tệp và Nhập được đếm theo mã học khu của bang. Một bảng của học khu hành chính chung (supervisory union) được ghi cho từng học khu thành viên, nên số bảng ghi vào D1 có thể lớn hơn. Bảng ghi vào D1 gồm bản published và bản draft chờ xem tay.

## Học khu bỏ qua và lý do

| Bang | Năm học | Mã của bang | Tên trong tệp | Lý do |
|---|---|---|---|---|
| CA | 2023-24 | 1062240 | KINGSBURG JOINT UNION ELEMENTA | NCES 0619800 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2023-24 | 1663933 | ISLAND UNION ELEMENTARY | NCES 0618510 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2023-24 | 1663941 | KINGS RIVER-HARDWICK UNION ELE | NCES 0619770 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2023-24 | 1663990 | PIONEER UNION ELEMENTARY | NCES 0630510 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2023-24 | 3166761 | ACKERMAN ELEMENTARY | NCES 0601680 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2023-24 | 5071100 | HICKMAN ELEMENTARY | NCES 0617160 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2024-25 | 1663933 | ISLAND UNION ELEMENTARY | NCES 0618510 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2024-25 | 1663990 | PIONEER UNION ELEMENTARY | NCES 0630510 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2024-25 | 3166761 | ACKERMAN ELEMENTARY | NCES 0601680 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |
| CA | 2024-25 | 5071100 | HICKMAN ELEMENTARY | NCES 0617160 (LEA_TYPE 7 Independent charter district) nằm ngoài danh mục học khu của site (D-015) |

## Lý do chuyển xem tay

| Bang | Năm học | Kiểm tra | Số bảng |
|---|---|---|---:|
| CA | 2023-24 | monotonic_lane | 74 |
| CA | 2023-24 | monotonic_step | 15 |
| CA | 2024-25 | cross_check | 3 |
| CA | 2024-25 | monotonic_lane | 71 |
| CA | 2024-25 | monotonic_step | 21 |
| CA | 2024-25 | start_change | 4 |
| KY | 2024-25 | monotonic_lane | 3 |
| KY | 2024-25 | monotonic_step | 13 |
| KY | 2025-26 | monotonic_lane | 3 |
| KY | 2025-26 | monotonic_step | 7 |
| KY | 2025-26 | start_change | 1 |

## Học khu còn thiếu bảng lương ở mỗi bang

Học khu đang hoạt động trong danh mục của site nhưng không có bảng lương năm mới nhất từ tệp của bang. Các học khu này chuyển sang pipeline PDF (Công đoạn 5).

- **CA** (2024-25): 159 / 988 học khu còn thiếu (83.9% đã có).

  <details><summary>Danh sách</summary>

  - Acton-Agua Dulce Unified (NCES 0600001)
  - Alexander Valley Union Elementary (NCES 0601890)
  - Alpine County Office of Education (NCES 0691058)
  - Alta-Dutch Flat Union Elementary (NCES 0602250)
  - Amador County Office of Education (NCES 0691001)
  - Amador County Unified (NCES 0602450)
  - Aromas - San Juan Unified (NCES 0691136)
  - Banning Unified (NCES 0603840)
  - Beardsley Elementary (NCES 0604260)
  - Bella Vista Elementary (NCES 0604350)
  - Belleview Elementary (NCES 0604500)
  - Benicia Unified (NCES 0604620)
  - Big Creek Elementary (NCES 0604860)
  - Big Lagoon Union Elementary (NCES 0604890)
  - Blake Elementary (NCES 0605250)
  - Bonsall Unified (NCES 0601426)
  - Borrego Springs Unified (NCES 0605700)
  - Bradley Union Elementary (NCES 0605730)
  - Bridgeville Elementary (NCES 0606000)
  - Buellton Union Elementary (NCES 0606330)
  - Burlingame Elementary (NCES 0606480)
  - Burrel Union Elementary (NCES 0606540)
  - Butteville Union Elementary (NCES 0606690)
  - Byron Union Elementary (NCES 0606750)
  - Calaveras Unified (NCES 0606870)
  - Caliente Union Elementary (NCES 0606960)
  - Cambrian (NCES 0607140)
  - Castle Rock Union Elementary (NCES 0607770)
  - Chatom Union (NCES 0608250)
  - Chicago Park Elementary (NCES 0608340)
  - Chowchilla Elementary (NCES 0608520)
  - Coffee Creek Elementary (NCES 0609240)
  - Colfax Elementary (NCES 0609300)
  - College Elementary (NCES 0609330)
  - Curtis Creek Elementary (NCES 0610320)
  - Del Norte County Unified (NCES 0610770)
  - Dos Palos Oro Loma Joint Unified (NCES 0600033)
  - Douglas City Elementary (NCES 0611430)
  - Ducor Union Elementary (NCES 0611550)
  - Dunham Elementary (NCES 0611610)
  - El Monte City (NCES 0612090)
  - El Rancho Unified (NCES 0612180)
  - Farmersville Unified (NCES 0600035)
  - Fieldbrook Elementary (NCES 0613740)
  - Fresno County Office of Education (NCES 0691007)
  - Garfield Elementary (NCES 0614910)
  - Gazelle Union Elementary (NCES 0614970)
  - General Shafter Elementary (NCES 0615000)
  - Gold Trail Union Elementary (NCES 0615450)
  - Golden Feather Union Elementary (NCES 0615480)
  - Golden Plains Unified (NCES 0691134)
  - Gonzales Unified (NCES 0600046)
  - Gorman Joint (NCES 0615600)
  - Green Point Elementary (NCES 0615990)
  - Guadalupe Union Elementary (NCES 0616260)
  - Happy Camp Union Elementary (NCES 0616530)
  - Happy Valley Union Elementary (NCES 0616570)
  - Hilmar Unified (NCES 0617220)
  - Hornbrook Elementary (NCES 0617620)
  - Hot Springs Elementary (NCES 0617640)
  - Howell Mountain Elementary (NCES 0617760)
  - Hughes-Elizabeth Lakes Union Elementary (NCES 0617880)
  - Imperial County Office of Education (NCES 0691010)
  - Indian Diggings Elementary (NCES 0618240)
  - Johnstonville Elementary (NCES 0619050)
  - Julian Union Elementary (NCES 0619140)
  - Julian Union High (NCES 0619110)
  - Junction City Elementary (NCES 0619170)
  - Junction Elementary (NCES 0619230)
  - Kashia Elementary (NCES 0632340)
  - Kentfield Elementary (NCES 0619380)
  - Kenwood (NCES 0619410)
  - Kings River Union Elementary (NCES 0619740)
  - Klamath River Union Elementary (NCES 0619920)
  - Klamath-Trinity Joint Unified (NCES 0619950)
  - Lagunitas Elementary (NCES 0620520)
  - Lakeside Joint (NCES 0620700)
  - Lakeside Union (NCES 0620730)
  - Lakeside Union Elementary (NCES 0620760)
  - Las Lomitas Elementary (NCES 0622380)
  - Latrobe (NCES 0621180)
  - Lemoore Union Elementary (NCES 0621360)
  - Lewiston Elementary (NCES 0621480)
  - Linns Valley-Poso Flat Union (NCES 0621900)
  - Lompoc Unified (NCES 0622410)
  - Lone Pine Unified (NCES 0622440)
  - Loomis Union Elementary (NCES 0622560)
  - Los Nietos (NCES 0622890)
  - Luther Burbank (NCES 0623130)
  - Maricopa Unified (NCES 0623820)
  - Marin County Office of Education (NCES 0691018)
  - Mariposa County Office of Education (NCES 0691090)
  - McKinleyville Union Elementary (NCES 0624300)
  - Merced River Union Elementary (NCES 0624630)
  - Meridian Elementary (NCES 0624690)
  - Miller Creek Elementary (NCES 0611220)
  - Montgomery Elementary (NCES 0625650)
  - Mountain Empire Unified (NCES 0626100)
  - Mountain Union Elementary (NCES 0627040)
  - Napa County Office of Education (NCES 0691022)
  - New Jerusalem Elementary (NCES 0627030)
  - Newman-Crows Landing Unified (NCES 0627200)
  - Norris Elementary (NCES 0627450)
  - North Monterey County Unified (NCES 0627590)
  - Northern Humboldt Union High (NCES 0603030)
  - Oak Run Elementary (NCES 0627870)
  - Old Adobe Union (NCES 0628320)
  - Orange Center (NCES 0628530)
  - Outside Creek Elementary (NCES 0629160)
  - Owens Valley Unified (NCES 0629190)
  - Pacific Union Elementary (NCES 0629400)
  - Pacifica (NCES 0620460)
  - Penn Valley Union Elementary (NCES 0601427)
  - Pleasant Grove Joint Union (NCES 0630900)
  - Plumas County Office of Education (NCES 0691102)
  - Pollock Pines Elementary (NCES 0631290)
  - Pond Union Elementary (NCES 0631350)
  - Pope Valley Union Elementary (NCES 0631380)
  - Red Bluff Union Elementary (NCES 0631980)
  - Redwood City Elementary (NCES 0632130)
  - Richmond Elementary (NCES 0632520)
  - San Antonio Union Elementary (NCES 0634050)
  - San Francisco County Office of Education (NCES 0691111)
  - San Lucas Union Elementary (NCES 0634770)
  - Sebastopol Union Elementary (NCES 0636180)
  - Seeley Union Elementary (NCES 0636210)
  - Seiad Elementary (NCES 0636240)
  - Sierra County Office of Education (NCES 0691120)
  - Silver Fork Elementary (NCES 0636810)
  - Silver Valley Unified (NCES 0636820)
  - Siskiyou County Office of Education (NCES 0691038)
  - Siskiyou Union High (NCES 0636940)
  - Sonora Union High (NCES 0637260)
  - South Pasadena Unified (NCES 0637500)
  - Southern Humboldt Joint Unified (NCES 0637590)
  - Spencer Valley Elementary (NCES 0637680)
  - Stony Creek Joint Unified (NCES 0638070)
  - Traver Joint Elementary (NCES 0639600)
  - Tres Pinos Union Elementary (NCES 0639690)
  - Trinidad Union Elementary (NCES 0639720)
  - Trinity Center Elementary (NCES 0639750)
  - Twin Ridges Elementary (NCES 0600012)
  - Two Rock Union (NCES 0640260)
  - Union Hill Elementary (NCES 0640380)
  - Vineland Elementary (NCES 0641130)
  - Washington Colony Elementary (NCES 0641460)
  - Waugh Elementary (NCES 0641790)
  - Weaver Union (NCES 0641880)
  - Weed Union Elementary (NCES 0641980)
  - West Park Elementary (NCES 0642060)
  - West Side Union Elementary (NCES 0642270)
  - Westside Elementary (NCES 0642210)
  - Wheatland (NCES 0642330)
  - Wheatland Union High (NCES 0642350)
  - Willow Creek Elementary (NCES 0642600)
  - Wilmar Union Elementary (NCES 0642750)
  - Wilsona Elementary (NCES 0642810)
  - Wiseburn Unified (NCES 0601428)
  - Woodside Elementary (NCES 0643140)

  </details>

- **KY** (2025-26): 0 / 171 học khu còn thiếu (100.0% đã có).

## Mẫu ngẫu nhiên để kiểm tra chéo

10 học khu mỗi bang (năm mới nhất, bảng published, chọn ngẫu nhiên có seed). Phần lớn học khu nhỏ không đăng bảng lương công khai, nên kiểm tra chéo dùng thêm học khu có tài liệu; kết quả ở docs/reports/state-schedules-crosscheck.md.

| Bang | Học khu | NCES | Năm học | Ô đầu tiên | Ô lớn nhất |
|---|---|---|---|---:|---:|
| CA | Lake Tahoe Unified | 0620640 | 2024-25 | $60,469 | $128,797 |
| CA | Big Oak Flat-Groveland Unified | 0691137 | 2024-25 | $55,272 | $100,425 |
| CA | Rancho Santa Fe Elementary | 0631740 | 2024-25 | $65,365 | $139,722 |
| CA | Rialto Unified | 0632370 | 2024-25 | $64,211 | $132,726 |
| CA | Lucerne Elementary | 0623040 | 2024-25 | $54,102 | $99,781 |
| CA | Liberty Elementary | 0621540 | 2024-25 | $71,964 | $126,863 |
| CA | Cinnabar Elementary | 0608700 | 2024-25 | $56,129 | $104,350 |
| CA | Kirkwood Elementary | 0619860 | 2024-25 | $46,020 | $85,611 |
| CA | Paso Robles Joint Unified | 0600048 | 2024-25 | $57,254 | $108,860 |
| CA | Big Pine Unified | 0604950 | 2024-25 | $49,625 | $110,406 |
| KY | Anderson County | 2100120 | 2025-26 | $33,002 | $82,864 |
| KY | Paris Independent | 2104710 | 2025-26 | $35,231 | $70,024 |
| KY | Fulton County | 2102100 | 2025-26 | $25,306 | $68,942 |
| KY | Spencer County | 2105490 | 2025-26 | $34,421 | $78,131 |
| KY | Bourbon County | 2100540 | 2025-26 | $33,211 | $71,447 |
| KY | Bellevue Independent | 2100420 | 2025-26 | $30,642 | $83,991 |
| KY | Henry County | 2102760 | 2025-26 | $34,670 | $70,808 |
| KY | Knott County | 2103120 | 2025-26 | $36,716 | $73,571 |
| KY | Estill County | 2101760 | 2025-26 | $31,228 | $65,010 |
| KY | Somerset Independent | 2105430 | 2025-26 | $37,627 | $66,997 |
