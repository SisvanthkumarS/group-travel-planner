export default {
  'frontend/**/*.{ts,tsx,js,jsx}': [
    'eslint --max-warnings=0',
    'prettier --write',
  ],
  'frontend/**/*.{json,css,html}': 'prettier --write',
  '*.py': [
    'uv run --project backend ruff check',
    'uv run --project backend ruff format --check',
  ],
};
