import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The console spans four backends, so /api alone is not enough -- each path
// prefix is proxied to the service that owns it (ports per scripts/dev_up.ps1).
//
// /api/v1 goes to :8002 rather than :8001 on purpose: backend/app is a superset
// of the repo-root app (same auth/identity routes PLUS /clients + /investigate),
// so one target covers Part 1 and Part 4. :8001 404s the investigation routes.
// The previous target, :8000, is not where any service in this repo listens --
// every request 502'd.
const P1_P4 = process.env.VITE_API_TARGET || "http://127.0.0.1:8002"; // identity + investigation
const P3_P5 = process.env.VITE_RISK_TARGET || "http://127.0.0.1:8003"; // risk + governance
const P2 = process.env.VITE_ENTITY_TARGET || "http://127.0.0.1:8004"; // entity intelligence
const P1 = process.env.VITE_IDENTITY_TARGET || "http://127.0.0.1:8001"; // Part 1 standalone

const proxy = (target) => ({ target, changeOrigin: true });

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // /p1/* reaches the standalone Part 1 service. Needed because /api/v1/*
      // resolves to :8002, so without this there is no way to tell whether
      // :8001 itself is alive -- the health dot would report :8002 twice.
      "/p1": { target: P1, changeOrigin: true, rewrite: (p) => p.replace(/^\/p1/, "") },
      "/api": proxy(P1_P4),
      "/governance": proxy(P3_P5),
      "/risk": proxy(P3_P5),
      "/screen": proxy(P2),
      "/adverse-media": proxy(P2),
      "/customers": proxy(P2),
      "/ubo": proxy(P2),
      "/audit": proxy(P2),
    },
  },
});

