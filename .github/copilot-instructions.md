# Copilot instructions for `event-management-app`

## Build, test, and lint commands

This repository has **tests** but no dedicated build or lint configuration files.

```bash
# install runtime deps
pip install -r requirements.txt

# run full test suite
python -m pytest tests.py -q

# run a single test
python -m pytest tests.py::test_budget_add_item -q
```

## High-level architecture

- `app.py` is the composition root and route layer. It uses an app-factory (`create_app`) and also exposes a module-level `app = create_app()` for `flask run`/direct execution.
- `models.py` contains all persistence models (`Attendee`, `BudgetItem`) and the shared `FOOD_OPTIONS` pricing map used across registration, confirmation, dashboard, and budget calculations.
- Public flow: `/` → `/register` → `/confirmation/<attendee_id>`. Registration writes `Attendee` records and validates food choices against `FOOD_OPTIONS`.
- Organizer flow: `/login` sets `session["organizer"]`; protected pages (`/dashboard`, `/budget`, budget add/delete routes) all gate through `_require_organizer()`.
- Budget totals are computed dynamically at request time:
  - Food subtotal is derived from attendee food selections (`FOOD_OPTIONS` unit price × attendee counts).
  - Extras subtotal comes from persisted `BudgetItem` rows (`cost * quantity` via `BudgetItem.total`).
  - Grand total is `food_total + extras_total`.
- UI is server-rendered Jinja templates under `templates/`, all extending `templates/base.html`, which centralizes navigation, flash-message rendering, and local Bootstrap asset loading from `static/`.

## Key conventions in this codebase

- Keep business constants centralized in `models.py` (`FOOD_OPTIONS`) and consume them from routes/templates; do not duplicate food choices or prices in templates.
- Auth checks are route-local and explicit: call `_require_organizer()` at the start of each organizer-only view and return its redirect response when present.
- Validation/feedback pattern:
  - Validate form input in route handlers.
  - Use `flash(message, category)` with Bootstrap-compatible categories (`success`, `danger`, `warning`, `info`).
  - On validation failure, return the same page (or redirect back for budget POST routes) with flash feedback.
- Tests are written as request-level pytest tests in `tests.py` using a `client` fixture that creates a temp SQLite DB per test session via `create_app(test_config=...)`.
- Current organizer credentials used by tests/UI are `organizer` / `admin123` (password hashed in `app.py` at import time). If auth behavior changes, update tests accordingly.
- Static frontend dependencies (Bootstrap CSS/JS and icons) are committed under `static/` and referenced locally (not CDN).
