import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API runs separately (uv run uvicorn numidia_api.app:app).
// Point VITE_API_BASE at it; for local dev with a running API you can also
// uncomment the proxy and use '/api' as the base.
export default defineConfig({
  plugins: [react()],
  // server: { proxy: { "/api": "http://localhost:8000" } },
});