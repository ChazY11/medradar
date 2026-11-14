import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    // Hashed JS/CSS sit next to index.html rather than in an assets/ subdirectory. The
    // Python wheel installs the built UI as setuptools data-files, which flattens globs into
    // one directory; keeping the build flat means an installed wheel serves the same URLs as
    // a source checkout (see pyproject.toml "share/medradar/web").
    assetsDir: "",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8787",
        changeOrigin: true,
      },
    },
  },
});
