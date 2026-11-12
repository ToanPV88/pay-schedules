/** Kiểm tra token Turnstile phía server (developers.cloudflare.com/turnstile, Siteverify API). */

export const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

interface SiteverifyResponse {
  success: boolean;
  "error-codes"?: string[];
}

/** True khi Cloudflare xác nhận token. Lỗi mạng hoặc phản hồi lạ đều tính là thất bại. */
export async function verifyTurnstile(
  secret: string,
  token: string,
  remoteIp: string | null,
  fetcher: typeof fetch = fetch,
): Promise<boolean> {
  if (token === "" || token.length > 2048) {
    return false;
  }
  const body = new FormData();
  body.append("secret", secret);
  body.append("response", token);
  if (remoteIp) {
    body.append("remoteip", remoteIp);
  }
  try {
    const res = await fetcher(SITEVERIFY_URL, { method: "POST", body });
    if (!res.ok) {
      return false;
    }
    const outcome = (await res.json()) as SiteverifyResponse;
    return outcome.success === true;
  } catch {
    return false;
  }
}
