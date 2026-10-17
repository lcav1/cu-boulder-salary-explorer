# CU Boulder Salary Explorer

An interactive, static dashboard of **CU Boulder appointment records** from the [official CU Salary Database](https://www.cu.edu/budget/cu-salary-database).

- App: https://lcav1.github.io/cu-boulder-salary-explorer/
- Source: https://github.com/lcav1/cu-boulder-salary-explorer
- Bundled snapshot: [`data/salaries.json`](data/salaries.json)

## Run locally

Requires Python 3.9+; no Node, npm, build step, API key, or database is required.

```sh
python3 -m http.server 8000
```

Open http://localhost:8000. Serve the repository over HTTP; ES modules and JSON loading do not work by double-clicking `index.html`.

To collect the latest snapshot:

```sh
python3 -B scripts/refresh.py
```

Collection uses the Python standard library, follows source pagination, and intentionally spaces requests. Allow several minutes. Network access to `www.cu.edu` and the Caspio host linked from the page is required. Source rate limits may extend collection or cause a safe failure. Do not run multiple collectors at once.

## Explore

The four filters offer searchable checkboxes and multiple selections. Selections within a field are OR; fields combine with AND. Options always come from the complete snapshot, so incompatible choices produce an explicit empty state. Minimum full-time percentage is inclusive. At 0%, records with unknown full-time percentage remain visible; a positive minimum excludes them. Reset restores filters without erasing an entered salary.

All summary metrics, five visualizations, the sortable/paginated table, CSV export, and entered-salary comparison use the same filtered records. The histogram offers linear and log salary scales; log uses `log10(salary + 1)` so a zero salary is retained. The scatter plot draws every record with known salary and full-time percentage, including overlapping points. Its tooltip identifies a nearby record; the table exposes values for keyboard users. The job-family charts and department-group chart include **all** matching categories in scrollable panels. Department-group intervals show the middle 50%, rather than hiding variation behind a median.

The table shows only department name, roster ID, job title, job family, total salary, and full-time percentage. On narrow screens, these become labeled record cards with six sort controls, avoiding horizontal page or table scrolling. Hover or focus each row’s ⓘ for context and peer comparisons; click to keep the details open. Escape, the close control, or an outside click dismisses them. Campus, department group/detail, and employee record appear in those details. Downloaded CSV includes all source fields.

## Statistics and peer groups

All values are **source-reported annual base salaries**, not normalized to full-time equivalents or inflation adjusted. Dollar displays round to the nearest whole dollar for readability; calculations, the JSON snapshot, and CSV export retain source precision.

- **Records:** appointment rows, never a claimed employee count.
- **Full-time records:** rows whose full-time percentage is at least 100.
- **Median / P90 / quartiles:** sort known salaries; linearly interpolate at `(n − 1) × p`.
- **Average:** arithmetic mean of known salaries.
- **Salary percentile:** `100 × count(salary ≤ value) / number of known salaries`. Ties all receive the upper rank of their tie group. A one-record group has a 100th percentile for that record; that does not imply a strong comparison.
- **Range position:** `100 × (value − min) / (max − min)`. The numeric result is not clamped, so values outside the range remain clear. The marker stays within the visual track. Position is undefined when all salaries are equal.
- Missing salary is displayed as `—` and excluded from salary statistics and peer group sizes. Missing categorical fields display “Not reported”; missing full-time percentage is excluded from the scatter plot and similar-percentage peers. Actual zeros are preserved. Missing sort values stay last in either direction.

**Row peer groups always use the entire collected Boulder snapshot, independent of active dashboard filters.** Each group includes the current appointment when eligible:

1. Exact job title and exact department group.
2. Exact job title and full-time percentage within **±10 percentage points, inclusive**, across all Boulder departments. For a 50% appointment, this means 40–60%, not 45–55%.
3. All Boulder records with known salary.

Each comparison provides the group median, record salary minus median in dollars, percentile, and number of known salary records. Records with missing matching fields do not form artificial “unknown” peer groups. An unavailable record salary leaves its difference and percentile undefined. These are descriptive appointment-level comparisons; job titles and appointment percentages alone do not establish equivalent experience, duties, or pay equity.

## Collection and repeatability

[`scripts/refresh.py`](scripts/refresh.py) discovers the fiscal year **from the source page’s salary-information heading** and discovers that page’s Caspio embed URL. It does not infer a year from today’s date, roster IDs, or a hardcoded endpoint. It submits the source’s search form with `Value1_1=BOULDER` and rejects any returned campus other than `CU Boulder`. No other-campus salary records are collected or included.

The parser uses semantic report rows and omits Caspio’s duplicated responsive labels. The collector follows the actual “next page” links, checks the expected source header schema and total on every page, detects repeated pages, checks uniqueness and the final count, and rechecks fiscal year after collection. Unexpected schema, missing totals, conflicting identities, non-Boulder records, incomplete pages, and invalid numeric values fail the refresh. HTTP failures are retried with backoff; a failure preserves the last published snapshot. There is no fallback to fabricated or third-party data.

Identity is a hash of fiscal year, campus, roster ID, and employee record. When identity fields are missing, a deterministic full-row hash is used. A conflicting repeated appointment fails validation rather than silently overwriting a record. The process **replaces** a complete snapshot and never appends to it. Its canonical content hash makes identical reruns a no-op, preserving the prior collection timestamp. The JSON includes all requested fields, provenance, fiscal year, collection timestamp, source record count, page count, and content hash. A temporary file is renamed only after the full snapshot passes checks.

The bundled data allows reviewers to run the app and tests without accessing the source. [`tests/fixtures/source-report.html`](tests/fixtures/source-report.html) contains two actual first-page rows for parser regression testing; it is not the dashboard dataset.

## Monthly and manual refresh

[`.github/workflows/refresh.yml`](.github/workflows/refresh.yml) runs at **09:17 UTC on the first day of each month**. It also exposes **Actions → Refresh Boulder salary snapshot → Run workflow**. Locally, run the collector command above.

The workflow collects only Boulder, validates the snapshot, and commits changed data to `main`. It then explicitly dispatches the Pages workflow: pushes made with `GITHUB_TOKEN` do not themselves trigger push workflows. Unchanged data requires no redeployment. A failed refresh remains visible as a failed Actions run and leaves the live snapshot intact. Runs are serialized to avoid competing refresh commits. GitHub schedules can be delayed and may be disabled after prolonged inactivity in public repositories; manual dispatch remains available.

## GitHub Pages deployment

1. Push this repository to GitHub with `main` as its default branch.
2. In **Settings → Pages → Build and deployment**, select **GitHub Actions** as the source.
3. Ensure Actions are enabled, repository policies allow the listed official actions, and the `github-pages` environment permits deployment from `main`.
4. Push to `main` or run **Actions → Validate and deploy Pages → Run workflow**.

The Pages workflow runs collector/snapshot tests and Chromium browser tests against the actual bundled snapshot before publishing. It packages only `index.html`, `assets/`, `data/`, and `.nojekyll` using [`scripts/package_site.py`](scripts/package_site.py). No Python tooling, virtual environment, tests, or credentials are published. Relative asset URLs and `import.meta.url` support a GitHub Pages repository subpath. No routing rewrite or custom domain is required.

The refresh workflow needs `contents: write` and `actions: write`; deployment needs `pages: write` and `id-token: write`. These permissions are declared per workflow/job. No personal token or source-database credential is needed. Branch protection or organization restrictions on bot pushes/dispatch may require an administrator to allow this repository’s automation; the default workflow assumes bot pushes to `main` are allowed.

## Verify

Collector and snapshot tests use only Python’s standard library:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

For browser checks:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/e2e.py
```

On Linux CI, use `python -m playwright install --with-deps chromium`. The browser suite uses installed Google Chrome on macOS when available; set `CHROME_PATH` to choose an executable. It starts and stops its own local HTTP server. Screenshots are saved in ignored `test-results/` and uploaded as a CI artifact.

Tests cover actual source-markup parsing, year discovery, campus rejection, nulls, appointment identity, pagination, duplicate rejection, idempotence and preservation of the previous snapshot, actual snapshot integrity, independently calculated summary metrics, searchable and combined filters, full-time minimum, entered salary and range comparison, empty/reset behavior, sorting/pagination, all three row peer groups, CSV contents, chart updates, statistical edge cases, responsive layout/keyboard interaction, and dataset load failure.

## Architecture decisions and tradeoffs

- **Static HTML, CSS, and native JavaScript modules:** direct fit for GitHub Pages; no backend, framework build chain, runtime CDN, or third-party analytics. Plain state and pure statistical functions make the small application reviewable. A larger product would benefit from a component framework and typed data contracts.
- **Bundled JSON snapshot:** fast, reproducible, and available even if the source is offline. The entire snapshot is downloaded once and parsed in memory; this is appropriate for the current Boulder dataset, but substantially larger historical datasets would warrant compression, partitioning, or a worker. No salary values entered by visitors leave the browser or persist to storage.
- **Python standard-library collector:** minimal dependencies and explicit HTTP/form/pagination behavior. It depends on the public report markup and form contract, so schema checks fail visibly when the provider changes them. Conservative request pacing trades refresh speed for source reliability.
- **SVG histogram, canvas scatter, HTML comparison charts:** no external chart dependency; canvas handles all scatter records without thousands of DOM nodes. Overlapping scatter points can occlude one another, and canvas points are not individual keyboard targets; the full table and export expose their underlying data. Job-family and department-group labels remain selectable text with exact-value hover details.
- **Client-side statistics, sorting, and filtering:** immediate interaction without a server. Full-data peer indexes are built once, while exact similar-full-time comparisons are computed when a row is inspected. Only 25 table rows render at a time. This is designed for one campus snapshot, not an unrestricted multi-year warehouse.
- **Monthly checks of annual data:** fulfill repeatable refresh needs without implying that CU publishes monthly salary changes. The collected date is distinct from the fiscal-year label and the source’s fall-term snapshot date.

## Source limitations

The [CU Accountability Data Center](https://www.cu.edu/employee-services/accountability-data-center) states that the salary database is updated annually; excludes temporary workers, student employees, and retirees; and reflects a single point in time during the fall term. **Some source job titles contain “temporary” despite that published scope statement.** All Boulder records are retained as published; this dashboard does not guess employment status from title text.

The [CU Salary Database](https://www.cu.edu/budget/cu-salary-database) defines total salary as annual base salary from all funds, excluding allowances, bonuses, and contractual additions. Record counts are appointment counts. Employees with multiple appointments can appear more than once, and roster/ID information may need the employee-record identifier to distinguish appointments. The dashboard displays these limitations alongside the charts.

This project is an independent exploration of public data and is not an official CU application.
