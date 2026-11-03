#!/bin/sh
set -eu

node --input-type=module <<'NODE'
import { writeFileSync } from 'node:fs';

const config = {
  VITE_API_URL: process.env.VITE_API_URL || 'http://localhost:8000/api/v1',
};
writeFileSync(
  'dist/runtime-config.js',
  `globalThis.__APP_CONFIG__ = ${JSON.stringify(config)};\n`,
);
NODE

exec "$@"
