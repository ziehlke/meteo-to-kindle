# meteo-to-kindle Agent Guidelines

## Build/Test Commands
- Install dependencies: `uv sync`
- Run main script: `uv run get_image.py`
- Run tests: `uv run pytest` (with coverage: `uv run pytest --cov --cov-report=term-missing`)
- Tests live in `tests/`, network calls are mocked with respx, image assertions use synthetic PIL images
- Lint: `uv run ruff check .` (strict rule sets in `pyproject.toml` under `[tool.ruff.lint]`; `--fix` auto-fixes what it can)
- Format: `uv run ruff format .` (CI enforces it via `uv run ruff format --check .`)
- Type check: `uv run pyrefly check` (strict preset, configured in `pyproject.toml` under `[tool.pyrefly]`)
- Vulnerability check: `uv audit --preview-features audit-command`
- Interpreter: pinned via `.python-version` (3.12, the minimum from `requires-python`) - uv auto-uses it
- Secrets: `AIRLY_KEY` in `.env` (git-ignored); documented template in `.env.example`
- Dependencies defined in `pyproject.toml` (dev tools in the `dev` dependency group), exact versions pinned in `uv.lock`
- Dependabot (`.github/dependabot.yml`) opens grouped upgrade PRs weekly; CI (`.github/workflows/ci.yml`) runs ruff + pytest on every PR

## Code Style Guidelines
- Python 3.x with type hints where appropriate
- Import order: standard library, third-party, local imports
- Use f-strings for string formatting
- Environment variables via python-dotenv (.env file for API keys)
- Error handling with try/except blocks, retry logic for network requests
- Constants in UPPER_SNAKE_CASE at module level
- Class names in PascalCase, functions in snake_case
- Use PIL for image manipulation, numpy for bulk pixel operations, matplotlib for plotting (Agg backend)
- File paths using pathlib.Path with / operator for cross-platform compatibility
- Main execution in `if __name__ == '__main__':` block