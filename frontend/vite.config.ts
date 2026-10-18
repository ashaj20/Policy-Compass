/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on IPv4 explicitly so http://127.0.0.1:5173 and http://localhost:5173 both work on Windows.
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Generous limits so the suite stays reliable on a busy machine.
    testTimeout: 15000,
  },
});
