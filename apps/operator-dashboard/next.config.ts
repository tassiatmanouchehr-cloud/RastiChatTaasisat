import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets the production Dockerfile copy only .next/standalone + the traced
  // node_modules subset instead of the full dependency tree — see
  // docker/operator-dashboard.Dockerfile.
  output: "standalone",
};

export default nextConfig;
