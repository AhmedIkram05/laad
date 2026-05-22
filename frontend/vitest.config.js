import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Stub CSS imports during test — no empty files needed. */
function cssStubPlugin() {
  return {
    name: "css-stub",
    resolveId(id) {
      if (id.endsWith(".css")) return id;
    },
    load(id) {
      if (id.endsWith(".css")) return { code: "export default {}", map: null };
    },
  };
}

export default defineConfig({
  plugins: [react(), cssStubPlugin()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    include: ["src/**/*.{test,spec}.{js,jsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "lcov"],
      include: ["src/**"],
      exclude: [
        "src/test/**",
        "src/main.jsx",
      ],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
