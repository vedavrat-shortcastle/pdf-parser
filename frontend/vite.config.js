import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Standard Vite + React setup. The backend (FastAPI) runs separately on
// port 8000 with CORS enabled for this dev server's origin — see
// src/config.py CORS_ORIGINS. No proxy is configured here on purpose,
// so it's obvious in the network tab that this is two separate services
// talking over HTTP, not one process.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
