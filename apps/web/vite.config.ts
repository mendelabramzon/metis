import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The gateway mounts its routers at the root (no shared `/api` prefix), so the dev server
// forwards each top-level API prefix to it. The console at `/` stays the gateway's; the SPA
// is served by Vite in dev and from the gateway's static dir once it reaches parity (~M2).
const GATEWAY_PREFIXES = [
  "/users",
  "/organizations",
  "/workspaces",
  "/invites",
  "/actions",
  "/sources",
  "/telegram",
  "/query",
  "/wiki",
  "/skills",
  "/approvals",
  "/jobs",
  "/audit",
  "/providers",
  "/oauth",
  "/health",
];

// https://vitejs.dev/config/
export default defineConfig(() => {
  const gateway = process.env.VITE_GATEWAY_URL ?? "http://localhost:8000";
  const proxy = Object.fromEntries(
    GATEWAY_PREFIXES.map((prefix) => [prefix, { target: gateway, changeOrigin: true }]),
  );
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: { port: 5173, proxy },
    preview: { port: 5173, proxy },
    build: { outDir: "dist", sourcemap: true },
  };
});
