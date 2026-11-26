import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite on 127.0.0.1:5173 proxies /api to the read-only API (default 127.0.0.1:8765; set ATL_API to override,
// e.g. ATL_API=http://127.0.0.1:8766 when 8765 is taken by another program).
// Prod: `npm run build` -> dist/, served by the API itself (one origin, no CORS).
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": process.env.ATL_API ?? "http://127.0.0.1:8765" } },
  build: {
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("lightweight-charts")) return "charts";
          if (id.includes("node_modules")) return "vendor";
        },
      },
    },
  },
  test: { environment: "jsdom", globals: false },
});
