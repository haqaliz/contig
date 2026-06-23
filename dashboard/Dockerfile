# Multi-stage build for the Contig dashboard (PRD contract E). It produces a lean
# Next.js standalone server image. The image serves the dashboard ONLY; it does
# not bundle the `contig` engine CLI or the runs directory. At runtime point
# CONTIG_RUNS_DIR at a mounted runs volume and CONTIG_CMD / CONTIG_DISPATCH_CMD at
# a reachable `contig` CLI (a separate image or a host binary), and configure Auth0
# from env. See the Deploy section of the README.

# --- deps: install production-resolved dependencies once, cached on the lockfile.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- build: compile the app and emit the standalone server bundle.
FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runner: a minimal image that runs the standalone server as a non-root user.
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Run as an unprivileged user, not root.
RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# The standalone output carries its own minimal node_modules; copy it plus the
# static assets and the public directory into place.
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

# The standalone bundle's entrypoint. PORT and HOSTNAME above bind it on all
# interfaces inside the container; put a reverse proxy in front for TLS.
CMD ["node", "server.js"]
