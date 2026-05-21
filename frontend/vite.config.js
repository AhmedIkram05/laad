import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
    plugins: [react(), tailwindcss()],
    server: {
        proxy: {
            "/api/rag": "http://127.0.0.1:8000",
            "/api/analytics": "http://127.0.0.1:8000",
            "/api/insights": {
                target: "http://127.0.0.1:8000",
                rewrite: (path) => path.replace(/^\/api\/insights/, "/api/analytics"),
            },
            "/api": {
                target: "http://127.0.0.1:8000",
                rewrite: (path) => path.replace(/^\/api/, ""),
            },
            "/auth": "http://127.0.0.1:8000",
        },
        fallback: "index.html",
    },
});