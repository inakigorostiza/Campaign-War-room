import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Force a single three.js instance — react-globe.gl bundles its own copy, and a
  // material built from a second three instance is silently ignored (blank globe).
  resolve: { dedupe: ["three"] },
  server: {
    port: 5173,
    proxy: {
      // Proxy API + SSE to the Flask backend. `buffer` off so SSE flushes live.
      "/api": {
        target: "http://localhost:5001",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            proxyRes.headers["cache-control"] = "no-cache, no-transform";
          });
        },
      },
    },
  },
});
