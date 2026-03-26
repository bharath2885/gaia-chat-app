# =============================================================================
# Gaia Chat App — Frontend
# Multi-stage: Node build → nginx serve
# API calls are proxied through nginx so no hardcoded backend URL in the bundle.
# =============================================================================

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Point the app at the nginx proxy path (relative, works from any host)
ENV VITE_API_URL=/api/v1

RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config: SPA routing + backend proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
