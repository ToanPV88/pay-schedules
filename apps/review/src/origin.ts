/**
 * A form post from this site: the Origin header names this site, or the browser sent no usable
 * Origin ("null" or none) but marks the request same-origin (Sec-Fetch-Site).
 */
export function sameOriginPost(
  origin: string | undefined,
  fetchSite: string | undefined,
  url: string,
): boolean {
  if (origin && origin !== "null") return origin === new URL(url).origin;
  return fetchSite === "same-origin";
}
