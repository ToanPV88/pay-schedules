/**
 * Tên hiển thị của học khu, thành phố, quận (DECISIONS.md D-105).
 *
 * NCES giữ tên nguyên văn theo bang, một số bang viết hoa toàn bộ ("LITTLEFIELD ISD"). Tên có ít
 * nhất một chữ thường thì giữ nguyên; tên viết hoa toàn bộ thì đổi sang dạng Title Case, giữ nguyên
 * chữ viết tắt quen thuộc và số La Mã. Dữ liệu trong D1 không đổi.
 */

const ABBREVIATIONS = new Set([
  "CCSD",
  "CISD",
  "CSD",
  "CUSD",
  "DC",
  "ESD",
  "HSD",
  "ISD",
  "JUSD",
  "MSAD",
  "PSD",
  "RE",
  "RSU",
  "SAD",
  "SAU",
  "SD",
  "UESD",
  "UFSD",
  "UHSD",
  "USD",
]);

const SMALL_WORDS = new Set(["A", "AN", "AND", "AT", "FOR", "IN", "OF", "ON", "THE", "TO"]);

const ROMAN = /^(I{1,3}|IV|VI{0,3}|IX|XI{0,3})$/;

function fixPart(part: string, first: boolean): string {
  if (part === "" || ABBREVIATIONS.has(part) || /\d/.test(part)) {
    return part;
  }
  if (ROMAN.test(part) && !(first && part === "I")) {
    return part;
  }
  if (!first && SMALL_WORDS.has(part)) {
    return part.toLowerCase();
  }
  // "O'NEILL" -> "O'Neill"; "MARY'S" -> "Mary's".
  const lower = part.toLowerCase();
  const title = lower.charAt(0).toUpperCase() + lower.slice(1);
  return title.replace(/^(\p{L})'(\p{L})/u, (_m, a: string, b: string) => {
    return `${a}'${b.toUpperCase()}`;
  });
}

export function displayName(raw: string): string {
  if (/\p{Ll}/u.test(raw) || !/\p{Lu}/u.test(raw)) {
    return raw;
  }
  const words = raw.split(/(\s+)/);
  return words
    .map((word, i) =>
      word
        .split(/([-/.()])/)
        .map((part, j, parts) => fixPart(part, (i === 0 && j === 0) || parts[j - 1] === "("))
        .join(""),
    )
    .join("");
}

export function displayNameOrNull(raw: string | null): string | null {
  return raw === null ? null : displayName(raw);
}
