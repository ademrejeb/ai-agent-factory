FROM node:22-alpine AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-fund --no-audit

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./

# Rewrites are compiled into the build manifest, so the internal API origin is
# fixed at image build time. Rebuild the web image if the API host changes.
ARG API_ORIGIN=http://api:8080
ARG NEXT_PUBLIC_PLATFORM_NAME="AI Agent Factory"
ENV API_ORIGIN=$API_ORIGIN
ENV NEXT_PUBLIC_PLATFORM_NAME=$NEXT_PUBLIC_PLATFORM_NAME

RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3100 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3100
CMD ["node", "server.js"]
