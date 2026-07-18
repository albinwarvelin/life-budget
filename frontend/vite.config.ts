import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The dev proxy keeps browser requests same-origin during local development.
  // The API client still supports VITE_API_BASE_URL for a separately hosted API.
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
