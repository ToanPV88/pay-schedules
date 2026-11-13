# Kiểm tra `monotonic_lane` theo trình độ (D-024): đo trên tệp nguồn thật

Ngày: 2026-11-13. Đo tại máy, không tốn phút GitHub Actions: đọc lại tệp nguồn trong Release
`src-state-salaries-2425-20261112-43205697035` (J-90 2023-24 và 2024-25; tệp KY, hai năm mới nhất),
chạy riêng hai kiểm tra `monotonic_step` và `monotonic_lane` trước và sau thay đổi. Số đếm theo bảng
trong tệp của bang, trước khi ghép với danh mục học khu, nên có thể lệch vài bảng so với D1. Các
kiểm tra khác (`cross_check`, `start_change`) không đổi.

## Số bảng trượt hai kiểm tra

| Bang | Năm học | Bảng trong tệp | Trượt trước | Trượt sau | Được thả |
|---|---|---:|---:|---:|---:|
| CA | 2023-24 | 845 | 83 | 39 | 44 |
| CA | 2024-25 | 828 | 86 | 41 | 45 |
| KY | 2024-25 | 171 | 16 | 6 | 10 |
| KY | 2025-26 | 171 | 10 | 4 | 6 |
| **Tổng** | | | **195** | **90** | **105** |

Bảng trước đó qua mà nay trượt: 0.

## Bộ chuẩn PDF (30 bảng)

- Trước: publish 23, xem tay 7; ô đúng 2435/2435; 0 bảng sai lọt Validate.
- Sau: publish 24, xem tay 6; ô đúng 2560/2560; 0 bảng sai lọt Validate. Chatom 2024-25 được thả
  (lane NON-CRED đứng trước lane có chứng chỉ), 125/125 ô đúng.

## Bảng vẫn trượt hai kiểm tra sau thay đổi

Lý do đầu tiên của mỗi bảng. Đây là chỗ lạ thật của nguồn; người xem quyết định duyệt (đúng như nguồn)
hay loại.

| Bang | Năm học | Học khu | Lý do đầu tiên |
|---|---|---|---|
| CA | 2023-24 | ALUM ROCK UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 2, 'BA+30' $71,093.00 → 'BA+40' $69,440.00 |
| CA | 2023-24 | AUBURN UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 13, 'BA+60' $86,249.00 → 'BA+75' $84,533.00 |
| CA | 2023-24 | CHAFFEY UNION HIGH | Lương giảm khi lên lane trình độ cao hơn: bậc 9, 'BA' $94,471.00 → 'BA+15' $91,280.00 |
| CA | 2023-24 | ESCALON UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 18, 'BA+72+MA' $107,620.00 → 'BA+84+MA' $107,414.00 |
| CA | 2023-24 | FORESTVILLE UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 11, 'BA+45' $92,422.00 → 'BA+60' $92,114.00 |
| CA | 2023-24 | FORT BRAGG UNIFIED | Lương giảm khi tăng bậc: lane 'BA+75', bậc 17 $81,132.00 → bậc 18 $76,540.00 |
| CA | 2023-24 | FRESNO UNIFIED | Lương giảm khi tăng bậc: lane 'NON-CRED', bậc 5 $69,684.00 → bậc 11 $58,251.00 |
| CA | 2023-24 | HACIENDA LA PUENTE UNIFIED | Lương giảm khi tăng bậc: lane 'BA HALF STEP', bậc 23 $110,870.00 → bậc 24 $109,540.00 |
| CA | 2023-24 | HILLSBOROUGH CITY ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 15, 'BA+60' $149,734.00 → 'BA+75' $145,100.00 |
| CA | 2023-24 | JEFFERSON ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 3, 'BA+45' $66,920.00 → 'BA+60' $66,881.00 |
| CA | 2023-24 | KINGSBURG JOINT UNION ELEMENTA | Lương giảm khi lên lane trình độ cao hơn: bậc 40, 'BA+90' $127,697.00 → 'BA+90+MA' $127,552.00 |
| CA | 2023-24 | KLAMATH-TRINITY JOINT UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 11, 'BA+90 OR MA+45 AIE' $80,397.00 → 'BA+105 OR MA+60 AIE' $79,592.00 |
| CA | 2023-24 | LOS GATOS-SARATOGA JOINT UNION | Lương giảm khi lên lane trình độ cao hơn: bậc 4, 'BA+60+MA' $100,642.00 → 'BA+75+MA' $100,542.00 |
| CA | 2023-24 | MADERA UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 8, 'BA+15+CRED' $76,750.00 → 'BA+30+CRED' $74,366.00 |
| CA | 2023-24 | MAGNOLIA UNION ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+30', bậc 2 $54,998.00 → bậc 3 $54,145.00 |
| CA | 2023-24 | MIDWAY ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+72', bậc 11 $82,500.00 → bậc 12 $82,111.00 |
| CA | 2023-24 | NEEDLES UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 1, 'BA+15' $62,928.00 → 'BA+30 OR MA' $62,490.00 |
| CA | 2023-24 | NEW HAVEN UNIFIED | Lương đổi chiều giữa hai lane: bậc 2, 'BA<30' $87,993.00 → 'BA+30' $87,383.00 |
| CA | 2023-24 | NEW JERUSALEM ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 1, 'BA+30' $53,071.00 → 'BA+45' $49,634.00 |
| CA | 2023-24 | NEWCASTLE ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA<30 NON-CRED', bậc 3 $51,455.00 → bậc 4 $49,239.00 |
| CA | 2023-24 | NUESTRO ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+30', bậc 9 $74,669.00 → bậc 10 $70,442.00 |
| CA | 2023-24 | OJAI UNIFIED | Lương giảm khi tăng bậc: lane 'BA+15', bậc 8 $56,240.00 → bậc 9 $54,240.00 |
| CA | 2023-24 | OXNARD UNION HIGH | Lương giảm khi tăng bậc: lane '<BA', bậc 16 $110,751.00 → bậc 17 $103,892.00 |
| CA | 2023-24 | PACIFICA SCHOOL DISTRICT | Lương giảm khi lên lane trình độ cao hơn: bậc 29, 'BA+CRED' $94,038.00 → 'BA+40' $92,642.00 |
| CA | 2023-24 | PENINSULA UNION ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA', bậc 10 $59,455.00 → bậc 11 $59,308.00 |
| CA | 2023-24 | PLACER UNION HIGH | Lương đổi chiều giữa hai lane: bậc 12, 'CTE DSC' $83,377.00 → 'BA+CRED' $82,045.00 |
| CA | 2023-24 | PLUMAS COUNTY OFFICE OF ED. | Lương giảm khi lên lane trình độ cao hơn: bậc 15, 'BA+60 OR MA' $81,334.00 → 'BA+75 OR MA+15' $81,218.00 |
| CA | 2023-24 | POMONA UNIFIED | Lương giảm khi tăng bậc: lane 'BA+PRE-CRED OR INTERN', bậc 8 $76,842.00 → bậc 9 $73,356.00 |
| CA | 2023-24 | RIVERBANK UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 20, 'BA+78' $115,638.00 → 'BA+84' $114,735.00 |
| CA | 2023-24 | ROSEMEAD ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+45 OR MA CRED', bậc 8 $96,492.00 → bậc 9 $94,629.00 |
| CA | 2023-24 | ROSEVILLE JOINT UNION HIGH | Lương giảm khi lên lane trình độ cao hơn: bậc 23, 'BA+75' $128,153.00 → 'BA+90 OR MA+75' $125,946.00 |
| CA | 2023-24 | SALINAS UNION HIGH | Lương giảm khi tăng bậc: lane 'BA+60 OR MA+15', bậc 13 $118,820.00 → bậc 14 $110,923.00 |
| CA | 2023-24 | SANTA MARIA JOINT UNION HIGH | Lương giảm khi tăng bậc: lane 'BA+15', bậc 15 $94,865.00 → bậc 16 $94,474.00 |
| CA | 2023-24 | SCOTIA UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 1, 'BA+48' $45,231.00 → 'BA+60' $44,537.00 |
| CA | 2023-24 | SEELEY UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 16, 'BA+45 OR MA' $114,885.00 → 'BA+60+MA' $113,544.00 |
| CA | 2023-24 | TRACY JOINT UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 4, 'BA+30 EMERG/ INTERN' $63,655.00 → 'BA+45 EMERG/ INTERN' $63,581.00 |
| CA | 2023-24 | VACAVILLE UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 29, 'BA+45 NON-CRED' $103,937.00 → 'BA+60 NON-CRED' $103,567.00 |
| CA | 2023-24 | VENTURA COUNTY OFFICE OF ED. | Lương giảm khi lên lane trình độ cao hơn: bậc 9, 'BA' $85,108.00 → 'BA+30' $83,924.00 |
| CA | 2023-24 | WEST PARK ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+60', bậc 15 $80,619.00 → bậc 17 $80,296.00 |
| CA | 2024-25 | ALUM ROCK UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 2, 'BA+30' $71,093.00 → 'BA+40' $69,440.00 |
| CA | 2024-25 | BRENTWOOD UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 1, 'BA' $65,357.00 → 'BA+30' $64,027.00 |
| CA | 2024-25 | CABRILLO UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 6, 'BA+75 OR MA+30' $77,603.00 → 'BA+90 OR MA+45' $76,760.00 |
| CA | 2024-25 | CHAFFEY UNION HIGH | Lương giảm khi lên lane trình độ cao hơn: bậc 9, 'BA' $94,471.00 → 'BA+15' $91,280.00 |
| CA | 2024-25 | Cottonwood Union Elementary | Lương giảm khi lên lane trình độ cao hơn: bậc 4, 'BA+30' $58,248.00 → 'BA+45' $57,427.00 |
| CA | 2024-25 | CUTTEN ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+75', bậc 4 $68,772.00 → bậc 5 $67,102.00 |
| CA | 2024-25 | ETIWANDA ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+60+MA', bậc 32 $139,654.00 → bậc 33 $135,200.00 |
| CA | 2024-25 | FONTANA UNIFIED | Lương giảm khi tăng bậc: lane 'BA+70 OR BA+60+MA', bậc 26 $129,277.00 → bậc 27 $121,867.00 |
| CA | 2024-25 | FRESNO UNIFIED | Lương giảm khi tăng bậc: lane 'NON-CRED', bậc 10 $71,774.00 → bậc 11 $59,999.00 |
| CA | 2024-25 | GUERNEVILLE ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 4, 'BA' $66,134.00 → 'BA+30' $64,001.00 |
| CA | 2024-25 | HACIENDA LA PUENTE UNIFIED | Lương giảm khi tăng bậc: lane 'BA HALF STEP', bậc 23 $110,870.00 → bậc 24 $109,540.00 |
| CA | 2024-25 | Hanford Joint Union High | Lương giảm khi lên lane trình độ cao hơn: bậc 6, '<BA' $72,354.00 → 'BA' $69,636.00 |
| CA | 2024-25 | HILLSBOROUGH CITY ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 15, 'BA+60' $153,104.00 → 'BA+75' $148,365.00 |
| CA | 2024-25 | JEFFERSON ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 3, 'BA+45' $66,920.00 → 'BA+60' $66,881.00 |
| CA | 2024-25 | KERMAN UNIFIED | Lương giảm khi tăng bậc: lane 'BA+90', bậc 21 $112,891.00 → bậc 22 $112,191.00 |
| CA | 2024-25 | KINGS COUNTY OFFICE OF ED. | Lương giảm khi tăng bậc: lane 'BA+30', bậc 11 $79,653.00 → bậc 12 $76,953.00 |
| CA | 2024-25 | KINGSBURG JOINT UNION HIGH | Lương giảm khi tăng bậc: lane 'BA+90', bậc 19 $113,900.00 → bậc 20 $113,345.00 |
| CA | 2024-25 | MADERA UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 8, 'BA+CRED' $71,108.00 → 'BA+15+CRED' $70,215.00 |
| CA | 2024-25 | MAGNOLIA UNION ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+30', bậc 2 $54,998.00 → bậc 3 $54,145.00 |
| CA | 2024-25 | MIDWAY ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+72', bậc 11 $82,500.00 → bậc 12 $82,111.00 |
| CA | 2024-25 | MONTECITO UNION ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA', bậc 15 $100,282.00 → bậc 16 $100,081.00 |
| CA | 2024-25 | Murrieta Valley Unified | Lương giảm khi tăng bậc: lane 'BA+75 OR MA+30', bậc 18 $119,035.00 → bậc 19 $112,692.00 |
| CA | 2024-25 | NEEDLES UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 1, 'BA+15' $62,928.00 → 'BA+30 OR MA' $62,490.00 |
| CA | 2024-25 | NOVATO UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 23, 'BA+75 OR BA+60+MA' $119,705.00 → 'BA+75+MA+PHD' $119,249.00 |
| CA | 2024-25 | PENINSULA UNION ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA', bậc 10 $59,455.00 → bậc 11 $59,308.00 |
| CA | 2024-25 | PIEDMONT CITY UNIFIED | Lương giảm khi tăng bậc: lane 'BA+60 OR BA+45+MA', bậc 20 $99,812.00 → bậc 21 $95,973.00 |
| CA | 2024-25 | PINE RIDGE ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+45', bậc 14 $75,752.00 → bậc 15 $71,837.00 |
| CA | 2024-25 | PLACER UNION HIGH | Lương đổi chiều giữa hai lane: bậc 12, 'CTE/ DSC' $84,090.00 → 'BA+CRED' $82,747.00 |
| CA | 2024-25 | Ramona City Unified | Lương giảm khi lên lane trình độ cao hơn: bậc 15, 'MA' $101,416.00 → 'PHD' $100,797.00 |
| CA | 2024-25 | Riverbank Unified | Lương giảm khi lên lane trình độ cao hơn: bậc 25, 'BA+72' $117,658.00 → 'BA+78' $116,795.00 |
| CA | 2024-25 | Roseville City Elementary | Lương giảm khi tăng bậc: lane 'BA+60+CRED', bậc 15 $117,995.00 → bậc 16 $117,965.00 |
| CA | 2024-25 | ROUND VALLEY UNIFIED | Lương giảm khi lên lane trình độ cao hơn: bậc 1, 'BA+60' $65,848.00 → 'BA+75' $64,908.00 |
| CA | 2024-25 | SALINAS CITY ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 6, 'BA+60 OR MA+15' $91,809.00 → 'BA+75 OR MA+30' $89,167.00 |
| CA | 2024-25 | SAN BRUNO PARK ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 25, 'BA+31' $98,972.00 → 'BA+36' $97,942.00 |
| CA | 2024-25 | SAN MATEO COUNTY OFFICE OF ED. | Lương giảm khi tăng bậc: lane 'BA+45', bậc 16 $112,102.00 → bậc 17 $108,009.00 |
| CA | 2024-25 | SAN PASQUAL UNION ELEMENTARY | Lương giảm khi lên lane trình độ cao hơn: bậc 4, 'BA+60 OR MA' $65,354.00 → 'BA+75+MA OR PHD' $64,726.00 |
| CA | 2024-25 | SAUGUS UNION ELEMENTARY | Lương giảm khi tăng bậc: lane 'BA+MA OR PHD', bậc 25 $112,895.00 → bậc 26 $111,895.00 |
| CA | 2024-25 | TRACY JOINT UNIFIED | Lương giảm khi tăng bậc: lane 'BA+30 CRED', bậc 24 $89,034.00 → bậc 25 $85,610.00 |
| CA | 2024-25 | Valley Home Joint Elementary | Lương giảm khi lên lane trình độ cao hơn: bậc 28, 'BA+60+MA' $99,281.00 → 'BA+75+MA' $99,064.00 |
| CA | 2024-25 | VENTURA COUNTY OFFICE OF ED. | Lương giảm khi lên lane trình độ cao hơn: bậc 9, 'BA' $86,810.00 → 'BA+30' $85,602.00 |
| CA | 2024-25 | YOLO COUNTY OFFICE OF ED. | Lương giảm khi tăng bậc: lane 'BA+60', bậc 20 $96,070.00 → bậc 21 $95,255.00 |
| KY | 2024-25 | Augusta Independent | Lương giảm khi tăng bậc: lane 'Rank III', bậc 12 $45,963.00 → bậc 13 $45,846.00 |
| KY | 2024-25 | Fulton County | Lương giảm khi tăng bậc: lane 'Rank I', bậc 26 $64,688.26 → bậc 27 $64,668.26 |
| KY | 2024-25 | Mercer County | Lương giảm khi tăng bậc: lane 'Rank V', bậc 21 $49,809.00 → bậc 22 $49,696.00 |
| KY | 2024-25 | Murray Independent | Lương giảm khi tăng bậc: lane 'Rank I', bậc 15 $67,405.00 → bậc 16 $64,593.00 |
| KY | 2024-25 | Perry County | Lương giảm khi tăng bậc: lane 'Rank III', bậc 22 $56,514.00 → bậc 23 $55,464.00 |
| KY | 2024-25 | Robertson County | Lương đổi chiều giữa hai lane: bậc 0, 'Rank V' $31,875.00 → 'Rank IV' $30,016.00 |
| KY | 2025-26 | Augusta Independent | Lương giảm khi tăng bậc: lane 'Rank IV', bậc 5 $30,128.00 → bậc 6 $29,830.00 |
| KY | 2025-26 | Calloway County | Lương giảm khi tăng bậc: lane 'Rank IV', bậc 37 $33,280.00 → bậc 38 $33,208.00 |
| KY | 2025-26 | Elizabethtown Independent | Lương đổi chiều giữa hai lane: bậc 0, 'Rank V' $45,240.00 → 'Rank IV' $32,675.00 |
| KY | 2025-26 | Robertson County | Lương đổi chiều giữa hai lane: bậc 0, 'Rank V' $32,513.00 → 'Rank IV' $30,617.00 |
