/**
 * Tải một bảng lương dạng Excel (.xlsx), không dùng thư viện ngoài: tự ghép các tệp XML của
 * SpreadsheetML vào một tệp zip không nén (phương thức "stored"). Cùng nội dung với tệp CSV
 * (src/csv.ts), thêm định dạng tiền, hàng tiêu đề in đậm và độ rộng cột.
 */
import type { District, Schedule } from "@pay-schedules/db";
import { type SourceLines, sourceLines } from "./attribution";
import { SITE_NAME } from "./env";
import { escapeXml } from "./format";

// ---------------------------------------------------------------- zip

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc = (CRC_TABLE[(crc ^ byte) & 0xff] ?? 0) ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** Ngày giờ DOS cố định (1980-01-01 00:00) để cùng một bảng luôn ra cùng một tệp. */
const DOS_TIME = 0;
const DOS_DATE = (0 << 9) | (1 << 5) | 1;

/** Ghép các tệp thành một tệp zip không nén. */
export function zipStored(files: { name: string; data: Uint8Array }[]): Uint8Array<ArrayBuffer> {
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const file of files) {
    const name = encoder.encode(file.name);
    const crc = crc32(file.data);
    const size = file.data.length;

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true); // phiên bản cần để giải nén
    local.setUint16(6, 0x0800, true); // tên tệp mã hóa UTF-8
    local.setUint16(8, 0, true); // stored
    local.setUint16(10, DOS_TIME, true);
    local.setUint16(12, DOS_DATE, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, size, true);
    local.setUint32(22, size, true);
    local.setUint16(26, name.length, true);
    local.setUint16(28, 0, true);
    chunks.push(new Uint8Array(local.buffer), name, file.data);

    const entry = new DataView(new ArrayBuffer(46));
    entry.setUint32(0, 0x02014b50, true);
    entry.setUint16(4, 20, true);
    entry.setUint16(6, 20, true);
    entry.setUint16(8, 0x0800, true);
    entry.setUint16(10, 0, true);
    entry.setUint16(12, DOS_TIME, true);
    entry.setUint16(14, DOS_DATE, true);
    entry.setUint32(16, crc, true);
    entry.setUint32(20, size, true);
    entry.setUint32(24, size, true);
    entry.setUint16(28, name.length, true);
    entry.setUint32(42, offset, true);
    central.push(new Uint8Array(entry.buffer), name);

    offset += 30 + name.length + size;
  }
  const centralSize = central.reduce((sum, part) => sum + part.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true);
  end.setUint16(10, files.length, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, offset, true);

  const parts = [...chunks, ...central, new Uint8Array(end.buffer)];
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

// ---------------------------------------------------------------- bảng tính

/** Kiểu ô trong styles.xml: 0 thường, 1 đậm, 2 tiền chẵn đô, 3 tiền có xu, 4 chữ nghiêng xám. */
const STYLE = { plain: 0, bold: 1, dollars: 2, cents: 3, note: 4 } as const;

type SheetCell =
  | { kind: "text"; value: string; style?: number }
  | { kind: "money"; cents: number }
  | null;

/** Số cột → chữ cột Excel: 0 → A, 25 → Z, 26 → AA. */
export function columnName(index: number): string {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const rest = (n - 1) % 26;
    name = String.fromCharCode(65 + rest) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

// biome-ignore lint/suspicious/noControlCharactersInRegex: chính là để lọc ký tự điều khiển.
const XML_INVALID = /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g;

function cellXml(ref: string, cell: SheetCell): string {
  if (cell === null) {
    return "";
  }
  if (cell.kind === "money") {
    const style = cell.cents % 100 === 0 ? STYLE.dollars : STYLE.cents;
    return `<c r="${ref}" s="${style}"><v>${cell.cents / 100}</v></c>`;
  }
  // Chuỗi nội tuyến: Excel không hiểu là công thức dù bắt đầu bằng "=". Bỏ ký tự điều khiển mà
  // XML 1.0 không cho phép.
  const style = cell.style ?? STYLE.plain;
  const text = escapeXml(cell.value.replace(XML_INVALID, ""));
  return `<c r="${ref}" t="inlineStr" s="${style}"><is><t xml:space="preserve">${text}</t></is></c>`;
}

function sheetXml(rows: SheetCell[][], widths: number[]): string {
  const cols = widths
    .map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`)
    .join("");
  const body = rows
    .map((row, r) => {
      const cells = row.map((cell, c) => cellXml(`${columnName(c)}${r + 1}`, cell)).join("");
      return `<row r="${r + 1}">${cells}</row>`;
    })
    .join("");
  // Cố định hàng tiêu đề và cột bậc khi cuộn.
  return (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
    '<sheetViews><sheetView workbookViewId="0"><pane xSplit="1" ySplit="1" topLeftCell="B2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>' +
    `<cols>${cols}</cols><sheetData>${body}</sheetData></worksheet>`
  );
}

const STYLES_XML =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
  '<numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;$&quot;#,##0"/><numFmt numFmtId="165" formatCode="&quot;$&quot;#,##0.00"/></numFmts>' +
  '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font><font><i/><sz val="10"/><color rgb="FF666666"/><name val="Calibri"/></font></fonts>' +
  '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>' +
  '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
  '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
  '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
  '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>' +
  '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
  '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
  '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>' +
  '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>' +
  "</styleSheet>";

const CONTENT_TYPES_XML =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
  '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
  '<Default Extension="xml" ContentType="application/xml"/>' +
  '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
  '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
  '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
  '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>' +
  "</Types>";

const ROOT_RELS_XML =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
  '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>' +
  "</Relationships>";

/** Thuộc tính tệp (File > Info trong Excel): tiêu đề, người tạo, mô tả kèm nguồn và trang gốc. */
export function coreXml(notes: SourceLines, pageUrl: string): string {
  const description = `${notes.source}. ${notes.compiled}. ${notes.verify}`;
  return (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' +
    `<dc:title>${escapeXml(notes.heading)}</dc:title>` +
    `<dc:creator>${escapeXml(SITE_NAME)}</dc:creator>` +
    `<dc:description>${escapeXml(description)}</dc:description>` +
    `<dc:identifier>${escapeXml(pageUrl)}</dc:identifier>` +
    "</cp:coreProperties>"
  );
}

const WORKBOOK_RELS_XML =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
  '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' +
  "</Relationships>";

function workbookXml(sheetName: string): string {
  return (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
    `<sheets><sheet name="${escapeXml(sheetName)}" sheetId="1" r:id="rId1"/></sheets></workbook>`
  );
}

/**
 * Hàng đầu: "Step" và nhãn lane; mỗi hàng sau: nhãn bậc và số tiền. Ô trống có ghi chú thì ghi
 * ghi chú (chữ nghiêng). Sau một hàng trống: tên bảng, nguồn và lời nhắc đối chiếu.
 */
export function scheduleRows(
  district: District,
  schedule: Schedule,
  pageUrl: string,
): SheetCell[][] {
  const lanes = schedule.lanes.length > 0 ? schedule.lanes.map((l) => l.labelRaw) : ["Salary"];
  const rows: SheetCell[][] = [
    [
      { kind: "text", value: "Step", style: STYLE.bold },
      ...lanes.map((label): SheetCell => ({ kind: "text", value: label, style: STYLE.bold })),
    ],
  ];
  for (const [i, step] of schedule.steps.entries()) {
    const cells = (schedule.cells[i] ?? []).map((cell): SheetCell => {
      if (!cell) {
        return null;
      }
      if (cell.amountCents === null) {
        return { kind: "text", value: cell.note ?? "", style: STYLE.note };
      }
      return { kind: "money", cents: cell.amountCents };
    });
    rows.push([{ kind: "text", value: step.labelRaw, style: STYLE.bold }, ...cells]);
  }
  rows.push([]);
  const notes = sourceLines(district, schedule, pageUrl);
  rows.push([{ kind: "text", value: notes.heading }]);
  rows.push([{ kind: "text", value: notes.source }]);
  rows.push([{ kind: "text", value: notes.compiled }]);
  rows.push([{ kind: "text", value: notes.verify, style: STYLE.note }]);
  return rows;
}

/** Độ rộng cột theo nội dung của phần bảng (không tính các dòng nguồn bên dưới). */
function columnWidths(schedule: Schedule): number[] {
  const lanes = schedule.lanes.length > 0 ? schedule.lanes.map((l) => l.labelRaw) : ["Salary"];
  const stepWidth = Math.max(6, ...schedule.steps.map((s) => s.labelRaw.length + 2));
  return [Math.min(stepWidth, 30), ...lanes.map((l) => Math.min(Math.max(12, l.length + 2), 30))];
}

/** Tên trang tính: tối đa 31 ký tự, không chứa : \ / ? * [ ]. */
export function sheetName(schedule: Schedule): string {
  const name = `Salary ${schedule.schoolYear}`.replace(/[:\\/?*[\]]/g, " ");
  return name.slice(0, 31);
}

export function scheduleXlsx(
  district: District,
  schedule: Schedule,
  pageUrl: string,
): Uint8Array<ArrayBuffer> {
  const encoder = new TextEncoder();
  const rows = scheduleRows(district, schedule, pageUrl);
  const notes = sourceLines(district, schedule, pageUrl);
  const files = [
    { name: "[Content_Types].xml", data: encoder.encode(CONTENT_TYPES_XML) },
    { name: "_rels/.rels", data: encoder.encode(ROOT_RELS_XML) },
    { name: "docProps/core.xml", data: encoder.encode(coreXml(notes, pageUrl)) },
    { name: "xl/workbook.xml", data: encoder.encode(workbookXml(sheetName(schedule))) },
    { name: "xl/_rels/workbook.xml.rels", data: encoder.encode(WORKBOOK_RELS_XML) },
    { name: "xl/styles.xml", data: encoder.encode(STYLES_XML) },
    {
      name: "xl/worksheets/sheet1.xml",
      data: encoder.encode(sheetXml(rows, columnWidths(schedule))),
    },
  ];
  return zipStored(files);
}

export const XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export function xlsxFileName(district: District, schedule: Schedule): string {
  return `${district.slug}-${schedule.schoolYear}-salary-schedule-${schedule.id}.xlsx`;
}

export function xlsxPath(scheduleId: number): string {
  return `/schedules/${scheduleId}.xlsx`;
}
