FROM node:26-alpine AS builder
WORKDIR /workspace
ENV HUSKY=0
RUN npm install -g pnpm@12.15.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
RUN pnpm install --frozen-lockfile

COPY frontend/ ./frontend/
COPY tests/frontend/ ./tests/frontend/

RUN pnpm --dir frontend run build

FROM node:26-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN npm install -g serve@14.2.4
COPY --from=builder --chown=node:node /workspace/frontend/dist ./dist
COPY docker/frontend-entrypoint.sh /app/frontend-entrypoint.sh
COPY docker/frontend-serve.json /app/serve.json
USER node:node
EXPOSE 3000

ENTRYPOINT ["/bin/sh", "/app/frontend-entrypoint.sh"]
CMD ["serve", "-s", "dist", "-c", "/app/serve.json", "-l", "tcp://0.0.0.0:3000"]
