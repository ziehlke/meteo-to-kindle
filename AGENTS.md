# meteo-to-kindle Agent Guidelines

## Build/Test Commands
- Install dependencies: `uv sync`
- Run main script: `uv run get_image.py`
- Run tests: `uv run pytest` (with coverage: `uv run pytest --cov --cov-report=term-missing`)
- Tests live in `tests/`, network calls are mocked with respx, image assertions use synthetic PIL images
- Check syntax: `uv run python -m py_compile airly.py get_image.py config.py image_processor.py`
- Lint: `ruff check airly.py get_image.py config.py image_processor.py`
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