# Contributing to WalrusOS

Thank you for helping build the decentralized memory layer for AI! 🦭

## Quick Start

```bash
git clone https://github.com/walrusos/walrusos
cd walrusos
pip install -e ".[dev]"
pre-commit install
pytest tests/ -v
```

## Development Workflow

1. **Fork** the repo and create your branch: `git checkout -b feat/my-feature`
2. **Write tests first** — we practice TDD. Every new feature needs a test.
3. **Keep the engine pure** — `walrusos/engine/` must not import from `adapters/` or `sdk/`.
4. **Run the full suite** before opening a PR:

```bash
ruff check walrusos        # linting
ruff format walrusos       # formatting
mypy walrusos              # type checking
pytest tests/ -v           # unit + integration
python benchmarks/bench_suite.py  # perf regression check
```

## Architecture Principles

| Layer | Rule |
|---|---|
| `core/models/` | Pure Pydantic/SQLModel. Zero side effects. |
| `engine/` | Depends only on `core/`. No HTTP, no blockchain. |
| `adapters/` | Implements `engine/interfaces.py`. One per external system. |
| `sdk/` | Thin facade over `engine/` + `adapters/`. DX-first. |
| `cli/` | Thin facade over `sdk/`. No business logic. |
| `integrations/` | Depends on `sdk/` only. Optional extras. |

## Commit Style

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(memory): add fork() support for MemoryStream
fix(walrus): retry on 503 before raising WalrusError
docs(readme): add trading team example
test(engine): add property tests for DAG ordering
bench(memory): measure append throughput regression
```

## Reporting Issues

- **Bugs**: Open a GitHub issue with a minimal reproducible example.
- **Security**: See [SECURITY.md](SECURITY.md). Do **not** open a public issue.
- **Features**: Open a GitHub Discussion before implementing large changes.

## Code of Conduct

We follow the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind. Be constructive.
