# Production-grade frontend Dockerfile
# Multi-stage build: Node.js builder + nginx production
# 
# Stage 1: Builder (Node.js) - Installs deps, builds production assets
# Stage 2: Production (nginx alpine) - Serves static files + reverse proxies API

# ── Builder Stage ──────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files first (better layer caching)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code and build
COPY . ./
RUN npm run build

# ── Production Stage ────────────────────────────────────────────────────────
FROM nginx:alpine

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx runs on port 80 by default
EXPOSE 80

# Start nginx in foreground (Docker best practice)
CMD ["nginx", "-g", "daemon off;"]
