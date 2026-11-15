/**
 * "Districts near you" cho /calculator và /compare. Vị trí gần đúng lấy từ thông tin Cloudflare gắn
 * vào request (request.cf: quốc gia, bang, thành phố, toạ độ theo IP); không gọi dịch vụ ngoài, không
 * lưu IP hay vị trí. Trang HTML không đổi theo người xem (cache edge giữ nguyên, Google không index
 * nội dung theo vị trí): site.js gọi /api/nearby sau khi trang tải.
 */
import { listNearbyDistricts, type NearbyDistrict, stateCentroid } from "@pay-schedules/db";

export interface ApproxLocation {
  lat: number;
  lng: number;
  /** "Austin, Texas" hoặc "Texas": hiện cho người xem biết gợi ý dựa trên đâu. */
  label: string;
}

/** Phần của request.cf mà tính năng này dùng (kiểu của Cloudflare để mọi trường là tùy chọn). */
export interface CfLocation {
  country?: string;
  region?: string;
  city?: string;
  latitude?: string;
  longitude?: string;
}

/** Số học khu gợi ý. */
export const NEARBY_LIMIT = 8;
/** Khung tìm đầu tiên (±độ vĩ) và khung mở rộng khi quanh đó ít học khu có dữ liệu. */
const BOX_NEAR = 3;
const BOX_WIDE = 10;
/** Dưới số này ở khung gần thì mở rộng khung. */
const MIN_NEAR = 3;

function finite(value: string | undefined): number | null {
  if (value === undefined || value === "") {
    return null;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Vị trí từ request.cf: chỉ người xem ở Mỹ, có toạ độ. */
export function locationFromCf(cf: CfLocation | undefined): ApproxLocation | null {
  if (cf?.country !== "US") {
    return null;
  }
  const lat = finite(cf.latitude);
  const lng = finite(cf.longitude);
  if (lat === null || lng === null) {
    return null;
  }
  const label = [cf.city, cf.region].filter((x): x is string => Boolean(x)).join(", ");
  return { lat, lng, label: label || "the United States" };
}

/**
 * Tham số thử ở bản preview: `near=TX` (tâm bang) hoặc `near=30.27,-97.74`. Bản production bỏ qua
 * tham số này để không ai đổi được nội dung bằng cách sửa link.
 */
export async function locationFromParam(
  db: D1Database,
  near: string,
): Promise<ApproxLocation | null> {
  const value = near.trim();
  if (/^[A-Za-z]{2}$/.test(value)) {
    const centre = await stateCentroid(db, value.toUpperCase());
    return centre ? { lat: centre.lat, lng: centre.lng, label: centre.name } : null;
  }
  const match = /^(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)$/.exec(value);
  if (!match) {
    return null;
  }
  const lat = Number(match[1]);
  const lng = Number(match[2]);
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) {
    return null;
  }
  return { lat, lng, label: `${lat}, ${lng}` };
}

/** Khoảng cách theo đường tròn lớn, dặm (người xem ở Mỹ). */
export function milesBetween(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 3958.8 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

export interface NearbyHit {
  name: string;
  key: string;
  href: string;
  place: string;
  miles: number;
}

/**
 * Kết quả nhớ trong isolate theo ô toạ độ làm tròn 0.25 độ (~25 km), 1 giờ: nhiều người cùng khu vực
 * không làm D1 đọc lại.
 */
const CACHE_TTL_MS = 60 * 60 * 1000;
const CACHE_MAX = 500;
const cache = new Map<string, { at: number; value: Promise<NearbyDistrict[]> }>();

export function resetNearbyCache(): void {
  cache.clear();
}

async function nearestDistricts(db: D1Database, loc: ApproxLocation): Promise<NearbyDistrict[]> {
  const near = await listNearbyDistricts(db, loc.lat, loc.lng, NEARBY_LIMIT, BOX_NEAR);
  if (near.length >= MIN_NEAR) {
    return near;
  }
  return await listNearbyDistricts(db, loc.lat, loc.lng, NEARBY_LIMIT, BOX_WIDE);
}

export async function nearbyHits(db: D1Database, loc: ApproxLocation): Promise<NearbyHit[]> {
  const key = `${Math.round(loc.lat * 4) / 4},${Math.round(loc.lng * 4) / 4}`;
  const now = Date.now();
  let entry = cache.get(key);
  if (!entry || now - entry.at > CACHE_TTL_MS) {
    if (cache.size >= CACHE_MAX) {
      cache.clear();
    }
    entry = { at: now, value: nearestDistricts(db, loc).catch(() => []) };
    cache.set(key, entry);
  }
  const districts = await entry.value;
  return districts.map((d) => ({
    name: d.name,
    key: `${d.stateSlug}/${d.slug}`,
    href: `/${d.stateSlug}/${d.slug}`,
    place: d.city ? `${d.city}, ${d.stateCode}` : d.stateName,
    miles: Math.round(milesBetween(loc, d)),
  }));
}
