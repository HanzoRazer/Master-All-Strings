# Continuous Verification

Every pull request and every push to `main` runs the repository's engineering
gates in GitHub Actions, so repository health is reproducible in CI rather than
resting only on locally reported evidence.

The workflow is verification-only. It changes no runtime behavior and runs under
least privilege (`contents: read`).

## Canonical workflow

`.github/workflows/verify.yml` is the single verification workflow. Do not add a
second one; extend this file instead.

## Required gates

Each runs as a separate named step, so a failure is attributable to a specific gate
in the pull-request checks interface. The workflow fails if any gate fails.

| Step | Command | What it enforces |
| --- | --- | --- |
| Ruff lint | `ruff check src tests` | The configured lint rules (`E, F, I, B, UP`). Lint only — no formatter is enforced. |
| mypy strict | `mypy` | Strict-mode type checking over `src`. Strictness is enabled in `[tool.mypy]`, so no CLI flag is passed. Tests are not in scope. |
| pytest with coverage | `pytest --cov --cov-report=term-missing` | The full suite — including golden-vector and schema validation, which run inside pytest — and a repository-wide coverage floor. |

## Coverage policy

The floor is **95%**, repository-wide, defined once in `pyproject.toml`:

```toml
[tool.coverage.report]
fail_under = 95
```

It lives there, not in the workflow command, so a local `pytest --cov` enforces the
same policy CI does. The number is not duplicated in the workflow.

## Reproduce locally

```bash
pip install -e ".[dev]"

ruff check src tests
mypy
pytest --cov --cov-report=term-missing
```

These are the same commands the workflow runs, in the same order. A green local run
predicts a green CI run.

## Expected failures

- **Coverage below 95%** — `pytest` exits non-zero with
  `FAIL Required test coverage of 95% not reached`. Add tests or, for a genuinely
  unreachable defensive branch, justify it in review.
- **A lint or type failure** — fix the reported issue. Do not silence a gate to make
  the workflow pass.

## Scope boundary

This workflow automates the repository's *existing* engineering policy. It does not
introduce new standards. In particular it does not run `ruff format --check`;
formatter adoption, if it happens, is a separate Dev Order that measures the delta
and applies a baseline first, so mechanical formatting never rides along with a
behavioral change.

Passing CI is necessary for merge but not sufficient — it verifies engineering, not
architecture. Constitutional and design review remain a human responsibility.
