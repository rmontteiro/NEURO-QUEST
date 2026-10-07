# syntax=docker/dockerfile:1

FROM node:22.14.0-alpine AS build
WORKDIR /src
RUN --mount=type=bind,source=package.json,target=package.json \
    --mount=type=bind,source=package-lock.json,target=package-lock.json \
    --mount=type=secret,id=npmrc,target=/root/.npmrc,required=false \
    --mount=type=cache,target=/root/.npm \
    npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22.14.0-alpine AS runtime
WORKDIR /app
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup appuser
COPY --from=build --link --chown=1001:1001 /src/.next/standalone ./
COPY --from=build --link --chown=1001:1001 /src/.next/static ./.next/static
COPY --from=build --link --chown=1001:1001 /src/public ./public
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    BACKEND_URL=http://backend:8000
USER 1001:1001
EXPOSE 3000
LABEL org.opencontainers.image.title="lastro-frontend" \
      org.opencontainers.image.description="Mesa Lastro"
ENTRYPOINT ["node", "server.js"]
