import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "src/index.ts",
      name: "ClientMonitor",
      formats: ["iife", "es"],
      fileName: (format) => format === "iife" ? "client-monitor.min.js" : "client-monitor.es.js"
    },
    minify: "esbuild",
    sourcemap: true
  },
  test: {
    environment: "jsdom"
  }
});
