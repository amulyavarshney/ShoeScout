const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/$/, "")

/** Root-relative public files need the Pages base path. Absolute and protocol-relative URLs stay as they are. */
export function publicAsset(src: string): string {
  if (!BASE_PATH || !src.startsWith("/") || src.startsWith("//")) return src
  if (src === BASE_PATH || src.startsWith(`${BASE_PATH}/`)) return src
  return `${BASE_PATH}${src}`
}
