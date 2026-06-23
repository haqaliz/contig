import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone) so the Docker image can
  // run the app with only the traced node_modules, not the full install. See the
  // multi-stage Dockerfile and the deploy section of the README.
  output: "standalone",
};

export default nextConfig;
