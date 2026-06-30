import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy the chat API to the FastAPI backend during dev.
    proxy: { "/chat": "http://localhost:8000", "/healthz": "http://localhost:8000" },
  },
});
