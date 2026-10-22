import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: { port: 5173, strictPort: true },
  test: { include: ['../tests/frontend/**/*.test.ts'] },
});
