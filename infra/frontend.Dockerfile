FROM node:22-alpine
WORKDIR /workspace
ENV HUSKY=0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
RUN corepack enable && pnpm install --frozen-lockfile
COPY frontend/ ./frontend/
EXPOSE 5173
CMD ["pnpm", "run", "dev:frontend"]
