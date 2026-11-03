import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://localhost:7979";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // relative asset URLs: the server injects <base href="{URL base}/"> so the UI also works under a sub path
  base: command === "build" ? "./" : "/",
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/sonarr": { target: backend, changeOrigin: true },
      "/radarr": { target: backend, changeOrigin: true },
      "/feed": { target: backend, changeOrigin: true },
      "/ping": { target: backend, changeOrigin: true },
    },
  },
}));
