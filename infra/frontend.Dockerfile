FROM node:26-alpine
WORKDIR /workspace
ENV HUSKY=0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
RUN npm install -g pnpm@12.15.0 && pnpm install --frozen-lockfile
COPY frontend/ ./frontend/
EXPOSE 5173
CMD ["pnpm", "run", "dev:frontend"]
