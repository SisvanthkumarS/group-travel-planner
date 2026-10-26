FROM node:26-alpine AS builder
WORKDIR /workspace
ENV HUSKY=0
RUN npm install -g pnpm@12.15.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
RUN pnpm install --frozen-lockfile

COPY frontend/ ./frontend/
COPY tests/frontend/ ./tests/frontend/

ARG VITE_API_URL=http://localhost:8000/api/v1
RUN pnpm --dir frontend run build

FROM node:26-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN npm install -g serve@14.2.4
COPY --from=builder --chown=node:node /workspace/frontend/dist ./dist
USER node:node
EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "tcp://0.0.0.0:3000"]
