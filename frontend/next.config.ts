import type { NextConfig } from "next";

// GitHub Pages cannot run the Next server. STATIC_EXPORT builds the client
// storefront into `out/` at NEXT_PUBLIC_BASE_PATH (for example /ShoeScout).
const staticExport = process.env.STATIC_EXPORT === "true";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = {
  /* config options here */
  // The storefront is fully client-driven (live WebSocket session); cache components add no value here.
  cacheComponents: false,
  images: { unoptimized: true },
  ...(staticExport
    ? {
        output: "export" as const,
        trailingSlash: true,
        ...(basePath ? { basePath } : {}),
      }
    : {}),
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
