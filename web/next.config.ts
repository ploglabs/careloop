import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page here is a client-rendered dashboard reading live data from the API,
  // so Cache Components / partial prerendering add nothing.
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
