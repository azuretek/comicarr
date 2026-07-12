# Contributing to Comicarr

Thank you for your interest in contributing to Comicarr! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 22+
- [uv](https://docs.astral.sh/uv/) (recommended for Python dependency management)

### Getting Started

```bash
# Clone the repository
git clone https://github.com/frankieramirez/comicarr.git
cd comicarr

# Install Python dependencies
uv sync --extra dev

# Activate virtual environment
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install frontend dependencies (lockfile-respecting; matches CI)
cd frontend
npm ci
cd ..

# Install git pre-commit hooks (lint/format on commit)
pre-commit install

# Run the application
python3 Comicarr.py --nolaunch
```

### Dependency updates

`pyproject.toml` is the editable dependency declaration and `uv.lock` is the
committed resolution. Keep `requirements.txt` as the generated pip-compatible
export, never as a second source of dependency versions.

```bash
# Change pyproject.toml (or use uv add), then refresh the committed contract
uv lock
uv export --locked --no-dev --no-hashes --no-emit-project --output-file requirements.txt
uv run pytest tests/unit/test_dependency_manifests.py -q
```

### Pre-commit hooks

Hooks run automatically on `git commit` and mirror the CI lint/format checks:

- **Backend**: `ruff` (lint + autofix) and `ruff format` on `comicarr/`
- **Frontend**: Prettier and ESLint (via `frontend/` lockfile tools)

One-time install: `uv sync --extra dev && pre-commit install` (and `cd frontend && npm ci` for frontend hooks).

Useful commands:

```bash
pre-commit run --all-files   # run hooks on the whole tree
npm run lint                 # same checks CI uses (backend + frontend)
npm run lint:fix             # autofix what can be fixed
```

If a hook rewrites files, stage the changes and commit again. Avoid `git commit --no-verify` unless you have a deliberate reason — CI will still enforce the same rules.

### Frontend Development

```bash
cd frontend
npm run dev     # Start dev server with HMR
npm run lint    # Run ESLint
npm run typecheck  # Run TypeScript checks
npm run build   # Production build
```

When using `npm run dev` with a separately running backend, Comicarr defaults
to port **8090**. The Vite proxy targets `http://localhost:8090` (override with
`VITE_API_PROXY_TARGET` if needed).

### Running Tests

```bash
# Backend tests
pytest tests/unit -v
pytest tests/integration -v

# Frontend tests
cd frontend
npm run test:run
```

## Code Style

### Python

- **Formatting**: `ruff format comicarr/` is enforced in CI and by pre-commit; run it before pushing
- **Lint**: `ruff check comicarr/`
- **Type hints**: not required on large legacy modules; allowed in new `comicarr/app/**` code to match neighbors
- **Always catch specific exceptions** — use `except Exception as e`, never bare `except:`
- **Logging pattern**: `logger.fdebug('[MODULE-CONTEXT] message')` or `logger.error('[CONTEXT] Error: %s' % e)`
- **Config access**: `comicarr.CONFIG.option_name`
- **Database**: Always use parameterized queries — `db.DBConnection().action("SELECT * FROM table WHERE id=?", [id])`

### Frontend (React/TypeScript)

- React 19 with TypeScript
- Tailwind CSS 4 for styling
- TanStack Query for data fetching
- Radix UI for accessible components
- **Lint**: `cd frontend && npm run lint` (ESLint)
- **Format**: `cd frontend && npm run format` / `npm run format:check` (Prettier; enforced in CI and pre-commit)

### Import Ordering

1. Standard library imports
2. Third-party imports
3. Local imports: `from comicarr import logger, helpers`

### GPL License Header

All new Python files must include the GPL v3 license header at the top.

## Pull Request Process

1. Create a feature branch from `main` using a conventional prefix:
   ```
   feat/add-manga-search
   fix/metadata-parsing
   refactor/search-deduplication
   docs/api-guide
   chore/update-deps
   ```
2. Make your changes with clear, conventional commit messages (pre-commit hooks will lint/format staged files)
3. Ensure all tests pass and linting is clean (`npm run lint` from the repo root)
4. Open a PR — **the title must follow conventional commit format** (CI enforces this):
   ```
   feat: Add manga search provider
   fix: Correct metadata parsing for annual issues
   refactor: Extract search result deduplication
   docs: Update API configuration guide
   ```
5. Fill out the PR template

PR titles keep history readable, but they do not control releases. Add a changeset when the PR should affect the next app release.

## Releases

Releases are fully automated via [Changesets](https://github.com/changesets/changesets). **Do not manually create tags, bump versions, or create GitHub Releases.**

How it works:

1. For user-visible app changes, run `npm run changeset` and choose the bump type
2. For maintenance-only work, omit the changeset; CI will warn but will not block the PR
3. Changesets automatically maintains a `Version Packages` PR with changelog and version bumps
4. Merging the `Version Packages` PR creates the GitHub Release, git tag, and triggers the Docker image build

Version files (`package.json`, `pyproject.toml`, `frontend/package.json`, and lockfiles) are updated automatically — never edit versions by hand outside release automation.

## Reporting Issues

- Use the [Bug Report](https://github.com/frankieramirez/comicarr/issues/new?template=bug_report.md) template
- Include a CarePackage (available on the config page) when reporting bugs
- For feature requests, use the [Feature Request](https://github.com/frankieramirez/comicarr/issues/new?template=feature_request.md) template

## License

By contributing, you agree that your contributions will be licensed under the GPL v3 License.
