import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        proxy: {
            "/api": "http://127.0.0.1:8000",
            "/auth": "http://127.0.0.1:8000",
            "/anomalies": "http://127.0.0.1:8000",
            "/analysis": "http://127.0.0.1:8000",
        },
        fallback: "index.html",
    },
});
