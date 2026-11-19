// The Vite dev server, the frontend's only server (it runs in the frontend container).
// It proxies /api to the backend container, so the browser sees one origin: the session cookie
// works without CORS, and http://localhost:5173 is a secure context for the microphone.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://backend:8000" },
  },
});
