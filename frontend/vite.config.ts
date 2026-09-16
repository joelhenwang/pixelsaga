import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const root = dirname(fileURLToPath(import.meta.url));

const apiProxy = process.env["VITE_API_PROXY"] ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@gen": resolve(root, "../content/clients/worldsim.ts"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": apiProxy,
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": apiProxy,
    },
  },
});
