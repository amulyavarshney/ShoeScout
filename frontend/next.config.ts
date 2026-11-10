import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // The storefront is fully client-driven (live WebSocket session); cache components add no value here.
  cacheComponents: false,
  images: { unoptimized: true },
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
