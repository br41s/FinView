# FinView

Personal investment dashboard: multi-broker import, Spanish IRPF fiscal engine, options monitor, geopolitical signals.
Extends the workspace `CLAUDE.md`. Rules here are FinView-specific only.

Subsystem detail lives in `.claude/rules/` and loads automatically when you touch the matching files —
options, zonas-clave, geo-intel, importers/fiscal, alt-investments, segments, frontend, auth. Read one directly if you
need it before touching code.

Legal and data-protection obligations are mapped in `docs/compliance/README.md`.

---

## What this project is

- **Type**: Full-stack web app (personal tool, planning maybe upgrade SaaS)
- **Owner**: Brais — personal investment tracking across TR, DEGIRO, IBKR, ING, BBVA, eToro
- **Core value**: Unified view of dividends, capital gains, IRPF tax boxes, and live options intelligence

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12 · FastAPI · SQLAlchemy (create_all + ensure_columns, no Alembic) |
| Parsers | pdfplumber (PDF), openpyxl (XLSX), csv (IBKR) |
| Options data | yfinance · MEFF HTML scraping · Eurex RDF |
| AI | OpenRouter (hand-rolled httpx) — `settings.openrouter_model`, code default `deepseek/deepseek-v4-flash`, overridden in production by `FINVIEW_OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash` since 2026-10-10. One shared model for options analysis, the geo analyst and reading annual reports (segment notes, and what each says about AI). Every call goes through `llm_envelope.chat()`, which always sends `provider.data_collection: "deny"` (`PROVIDER_POLICY`; callers cannot override it). |
| Frontend | Next.js 16 · React 19 · TypeScript 6 · TailwindCSS · Recharts · lightweight-charts (price/candles) · NextAuth · shadcn/ui |
| DB prod | Neon Postgres |
| DB local | SQLite fallback |
| Deploy | Vercel (frontend) · Google Cloud Run europe-west1 (backend) |
| CI | Cloud Build trigger on push to backend/**, Dockerfile, pyproject.toml, cloudbuild.yaml |
| Tests | pytest · 1676 collected (all pass with files/; 148 skip without real broker PDFs/CSVs, on CI and in a local worktree alike) · vitest · 181 frontend tests |
| Linter | ruff (line-length 100) · ESLint (`cd frontend && pnpm lint`, eslint-config-next) |

---

## Dev start (always use venv)

Both at once: ./start.sh

Or separately:
- source .venv/bin/activate
- uvicorn backend.app:app --reload --port 8000 → localhost:8000
- cd frontend && pnpm dev → localhost:3000

Never run pip install outside .venv. Never use npm — frontend uses pnpm.

---

## Critical rules

- fifo_engine.py is the most sensitive file. Any change must be followed by full test suite.
  Never touch it without understanding cross-broker FIFO matching logic.
- FIFO v2 consumes the complete historical ledger through the target year, rejects
  future buys and incomplete inventory, and publishes only versioned results. A
  SPINOFF contributes quantity with unknown basis; if a target-year sale reaches it,
  publish no authoritative adjustment and surface `fifo_missing_cost_basis`; the
  source SPINOFF remains tracked separately as `missing_cost_basis`. Never apply
  legacy `calculation_version=NULL` rows to fiscal totals.
- Resolving `missing_cost_basis` reuses `set_price`: store the inherited per-share
  basis on the SPINOFF and recalculate from its trade year. A non-zero SPINOFF
  `net_amount_eur` means known basis; zero remains unknown.
- Any mutation of historical trades or imports must call `recalculate_fifo_from_year`
  using the earliest affected year. FIFO is stateful across years; recalculating only
  the file's nominal fiscal year leaves later sales stale.
- Transaction cash semantics are directional: BUY = gross + fees; SELL = gross − fees
  − withholding. Fiscal boxes round only after aggregation, with `ROUND_HALF_UP` cents;
  audit lots retain six decimals.
- Importer changes: each importer is isolated — changes in one must not break others.
  Always run pytest backend/tests/ after importer changes.
- Portfolio snapshots are authoritative only when
  `ImportRecord.portfolio_snapshot_complete=true`. Empty complete snapshots close old
  positions; partial ING/BBVA document sets must leave the marker false, and DEGIRO is
  complete only when its year-end certificate is present with every ISIN in it parsed. Holding rows
  from a `false` import are ignored by `_load_snapshots` (a partial list must never close
  the positions it omits, and a year with rows closes every ISIN it does not list);
  legacy `NULL` rows stay authoritative. Apply all later transactions after
  reconciliation and propagate unknown cost instead of zero.
- Portfolio totals are fail-closed: one unknown cost invalidates invested/P&L and one
  missing price invalidates total market value/P&L. Never publish a partial subtotal as
  the whole portfolio.
- Sector and region exposure on `/portfolio` comes from each issuer's own annual report
  (SEC 10-K XBRL for US ISINs, ESEF segment note for the rest) and is fail-closed: a
  breakdown is stored only if its lines add up to the report's tagged total revenue, and
  an amount read from an ESEF note by the model must appear in the note verbatim. A failed
  request or model call is never cached. See `.claude/rules/segments.md`.
- "Exposición a la IA" on `/portfolio` is what each issuer's own annual report says about
  AI (10-K Item 1A for US ISINs, the whole ESEF report for the rest): a mention count done
  in code and up to three quotes the model picks, published only if every quote is in the
  filing verbatim. No score or "risk of closure": no verifiable dataset exists for one, and
  it would read as advice. Next to it, an industry index FinView computes itself
  (Eloundou et al. 2024 occupation scores × BLS OEWS staffing, weighted by segment revenue)
  because the published AIIE table has no licence. The table is a committed JSON built by
  `scripts/build_ai_industry_exposure.py` from pinned versions. Same rules file.
- Portfolio price resolution is one ticker to many ISINs. Corporate-action ISINs that
  share a Yahoo ticker must all receive the fetched price and cache row.
- `/portfolio` prices the portfolio in parallel requests, so every write on that path is
  conflict-safe: `price_cache` rows are an `ON CONFLICT (isin, fetched_date)` upsert
  (`prices._upsert_price`), and a ticker learned during a valuation is committed per ISIN,
  with `IntegrityError` meaning a concurrent request stored it first. Check-then-insert
  raised UniqueViolation on the first view of the day (a 500, 2026-10-17).
- ISIN→ticker resolution lives in `services/ticker_map.py`, not in `prices.py`. Precedence
  is **manual > CURATED > yfinance**: an automatic lookup must not overwrite curated
  knowledge about a corporate action (AENA's pre/post-split ISINs share one ticker on
  purpose), and a user correction must beat both or a wrongly curated ISIN could only be
  fixed by a deploy. What the data supervisor resolves is persisted, so coverage widens
  with use instead of requiring a code change. A valuation learns too: an ISIN nothing
  resolves is looked up during the day's first real price fetch (`prices._learn_tickers`,
  its own 15s budget), never on a view where everything with a ticker is already cached
  — that would put a Yahoo call on every page load for a bond. Until 2026-10-17 only an
  import looked tickers up, and a dozen of the owner's holdings imported before `ticker_map`
  existed stayed unpriced. Whatever learns goes through `ticker_map.lookup`, which refuses
  a listing the price layer would value in the wrong currency (`valued_as_quoted`: the
  currency comes from the suffix and every `.L` is divided by 100) — Yahoo's ISIN lookup
  returned 1211.HK for BYD, a USD line on LSE and a Stuttgart line for EUR ETFs.
- Split history is cached in `split_history_cache` for 30 days. A failed Yahoo fetch is
  **not** cached — it returns the stale entry and retries next run. Caching a failure
  would pin "never split" on a real security for a month and the supervisor would miss
  the split it exists to catch. An empty result *is* cached: most tickers never split.
- yfinance's `timeout=` argument **does not bind**, so do not reach for it as a guard.
  `YfData._make_request` fetches the cookie/crumb with a hardcoded 30s default before
  every request: `yf.download(..., timeout=3)` still takes 30s against an endpoint that
  accepts the connection and never answers (measured), and `yf.Ticker(...).info` takes no
  timeout at all. Nothing is unbounded — curl_cffi maps a scalar timeout onto
  `CURLOPT_TIMEOUT` and `YfConfig.network.retries` is 0 — the damage is aggregate: one
  stalled request costs ~30s and the supervisor makes one per unresolved ISIN, so ~90
  ISINs is a 45-minute import (PR #255 → #258). Bound the **loop**, not the call, via
  `services/yahoo_budget.py` — 60s per import, 120s per geo cycle. A spent budget must
  degrade to whatever that path already did when Yahoo was unreachable, never to a
  cached failure. `threads=True` does not help: one global cookie lock serializes the
  stalls, so 3 tickers cost 4×30s, not 30s. A test asserting "a timeout is configured"
  passes while production hangs — assert the loop stops instead.
- DB schema: there is **no Alembic**. New tables auto-create via
  `Base.metadata.create_all` on startup. `create_all` does NOT alter existing tables, so
  adding a column to a table that already exists in prod requires registering it in
  `database._ADDITIVE_COLUMNS` (applied idempotently by `ensure_columns()` at startup).
  Dropping an obsolete UNIQUE constraint in prod (Postgres only) goes in
  `database._DROP_UNIQUE_CONSTRAINTS` (applied by `ensure_constraints()`); SQLite tables
  are rebuilt from the model and never carry it.
- A new table must be classified for data rights. `services/user_data.py` derives from the
  schema which tables belong to a user (a `user_id` column, or a foreign key into a table
  that has one) and uses that one definition for both the export (`GET /users/me/export`)
  and the account deletion (`POST /users/me/delete`). Anything else goes in `GLOBAL_TABLES`.
  `test_user_data.py` fails on an unclassified table: the pricing FAQ promised "elimina tu
  cuenta y todos tus datos" for months while nothing implemented it.
- Account deletion closes billing first and aborts if Stripe fails. An erased account that
  keeps being charged is worse than a deletion the user has to retry.
- The public legal documents (`frontend/src/app/legal/*`) state facts about the product.
  Keep them true in the same change: a new third party receiving user data goes in
  `PROCESSORS` (`src/lib/legal.ts`); analytics or any non-technical cookie needs a consent
  banner first; `/pricing` and the plan table in `/legal/condiciones` say exactly what
  `PLAN_LIMITS` enforces. A change users must re-accept bumps `TERMS_VERSION`
  (`services/auth_service.py`) and `LEGAL_UPDATED`.
- FinView shows data; it does not advise. Nothing a user reads may tell them to buy, sell,
  hold or size a position, or name a selection to invest in. Prompts that produce
  user-visible text import the rule from `services/llm_rules.py` (`test_llm_rules.py`
  enforces it); screens with signals or LLM text render `AiDisclaimer`, and hit rates render
  `PastPerformanceNote`. The wording is `NOT_ADVICE` in `frontend/src/lib/legal.ts`.
- Consent is stored, never assumed: registration is rejected without `accept_terms`, and
  `fiscal_profiles.disability` (health data) is only saved with `health_data_consent`.
- No breaking changes to API contracts without updating frontend src/lib/ types.
- API error `detail` a user can reach is written in Spanish; operator-only paths (cron
  rejection, Stripe webhook, `FINVIEW_*` config errors) stay English and are listed in
  `test_error_copy.py`, which fails the suite on an unlisted English string.
- Every frontend API call goes through `request()` in `src/lib/api.ts` (via `fetchJSON`,
  `send`, `postForm` or `download`). It owns the auth header, the single retry on a stale
  401, the sign-out when the retry is refused too, and the `res.ok` check. Never call
  `fetch` directly for `/api/*`: four hand-written deletes once reported success on a
  4xx/5xx and the item came back on reload. The backend token lives 90 days and the
  NextAuth `jwt` callback renews it through `POST /auth/refresh` once fewer than 7 days
  remain (`src/lib/tokenExpiry.ts`); before 2026-10-14 it was only minted at login, the
  cookie outlived it, and the app sent the dead token forever until the user guessed to
  sign out. The sign-out on a refused retry stays as the backstop.
- Never `.catch(() => {})` in the frontend. Use `bestEffort("label")` from
  `src/lib/bestEffort.ts` — it still swallows, but logs, so a persistent failure is
  findable. `bestEffort.test.ts` fails if a bare swallow comes back.
- options_scraper.py cache TTL (5 min) must not be removed — MEFF rate-limits scraping.
- Premium spikes compare each contract with its own previous close, statelessly. No learned
  baseline: the old in-memory EMA had no expiration in its key and was rebuilt on every cold
  start, so 99% of its alerts were term structure, not spikes (see `.claude/rules/options.md`).
- Claude analysis is fire-and-forget; non-availability must never break the agent cycle.
  Always guard: `if settings.openrouter_api_key and all_alerts`.
- Blog/MDX: in `.mdx` prose always escape `<` as `&lt;` — MDX parses `<1` (e.g. "FCF <1,2x")
  as a JSX tag start and breaks the whole Vercel build (see PR #101 → #105).
  Quick check: `grep -rn '<[0-9]' frontend/src/app/blog/*/page.mdx` must return nothing.
- A new blog post is **three** edits, and the build enforces it: the `page.mdx` directory,
  an entry in `app/blog/posts.ts`, and an illustration in `app/blog/postImages.tsx`.
  `blogPosts()` runs during static prerender and throws when the index and the filesystem
  disagree in either direction; a missing illustration is a `tsc` error. This exists because
  both had drifted: two cards linked to articles that never existed and two articles had no
  card. Order comes from `date`, so entry position does not matter.
- Merge gate: before merging ANY PR that touches `frontend/**`, run `gh pr checks <n>` and
  require the Vercel preview check green. Never merge on a red or pending preview.
- **CI runs on GitHub Actions** (`.github/workflows/ci.yml`): ruff + pytest on the
  backend, typecheck + vitest + build on the frontend, on every PR and every push to
  main. The earlier rule here said Actions "is not available on this account" and told
  you not to add a workflow — that premise was wrong and the workflow is restored.
  What is genuinely unavailable is **branch protection** (403, Free plan), so a red
  check cannot mechanically block a merge: it is a signal, not a wall. Never merge on
  red.
- The other two gates still stand and are not superseded: `.githooks/pre-push` (same
  checks, locally, before the push) and the Vercel preview. Enable the hook once per
  clone with `git config core.hooksPath .githooks`; `start.sh` does this for you.

---

## Deploy

- Frontend: push to main → Vercel auto-deploys. No action needed.
- Backend: push to main touching backend/**, Dockerfile, pyproject.toml, or cloudbuild.yaml
  → Cloud Build triggers → deploys to Cloud Run europe-west1.
- Never touch cloudbuild.yaml without knowing what you are doing — it controls prod deploys.
- Backend deps are pinned: the Dockerfile installs from requirements.txt (hash-locked,
  exported from uv.lock). After ANY pyproject.toml dependency change run
  `uv lock && uv export --frozen --no-dev --no-emit-project -o requirements.txt` and commit
  both files — `backend/tests/test_requirements_sync.py` fails the suite if you forget.
- Cloud Run runtime flags in cloudbuild.yaml are load-bearing: `--cpu-throttling` +
  `--cpu-boost` + `--min=0` + `--max=1` + `--max-instances=1` + `--memory=1Gi`, with
  `FINVIEW_REQUEST_SCOPED_RUNTIME=true`. Production work must finish inside HTTP requests;
  never restore startup/background workers or `--no-cpu-throttling` to hide cold-start latency.
- Revisions are named `finview-api-$SHORT_SHA-$BUILD_ID`, one per build: a failed candidate
  named after its commit could never be deleted (latest created revision) and blocked every
  retry of that commit.
- Deploys are candidate-first: image smoke test on `PORT=8080`, private revision with 0% traffic,
  startup/configuration guard, promotion, public readiness recheck, rollback on failure.
  A successful build or `gcloud deploy` is not evidence that production is healthy.
- Full deploy docs: docs/deployment.md

---

## Tests

Backend: `pytest` — 1676 collected (all under `backend/tests/`). On the main machine, with
the real broker files in `files/`, all 1676 pass in ~110s. Those files are not in the repo,
so where `files/` is absent — CI, and worktrees unless you symlink it — 148 skip and the
remaining 1528 run in ~80s. It is one number again: until 2026-10-05 it was 159 on CI and
127 in a worktree, and the 32 between them were `test_ing.py` (below). The geo suite is
the largest block (`test_geo_*`): it pins the
notify gate's reachability from the real rule catalogue, the scope-vs-breadth invariant, the
GDELT export parser, the v2 checkpoint scorer, and the country layer (template rules stay
out of a signal's scoring, an event only reaches its own country's instruments, each rule
learns from its own legs, the ladder reads tiers without moving a confidence) — see `.claude/rules/geo.md`.

A skipped test reports as a pass, so a broken gate hides silently: the 35 tests in
`test_tr_parser.py` were gated on a hardcoded `~/Downloads` path that no longer existed
and ran nothing for months. `test_ing.py` failed the other way round: its gate was an
absolute path into the main clone, so all 32 ran on the owner's machine from any checkout
and all 32 skipped in CI, the 11 that need no PDF included — and a tree without `files/`
reported 127 skips here against 159 there. Gate on a path built from
`Path(__file__).resolve().parents[2] / "files"`, and put the gate where the dependency
is — a fixture that calls `pytest.skip()`, not a module-level `pytestmark` that also takes
the pure unit tests down with it.

Frontend: `cd frontend && pnpm test` (vitest) — 181 tests over pure logic: `src/lib/`
(`aiExposure`, `brokerSync`, `exposure`, `optionsWatchlistSync`, `optionsWatchlistRows`, `portfolioValues`, `apiError`, `bestEffort`,
`format`, `geoHealth`, `geo` — accuracy line, tradability hint, scope label, chained thesis, tier grouping, ladder badge)
plus `src/app/blog/posts.test.ts`, `src/app/options/optionsData.test.ts` (the options
page's state reducer) and `src/game/garden/` (the rules of the landing page's garden game). **`vitest` must be installed**
or `pnpm build` fails on `vitest.config.ts` even though the app itself compiles — run
`pnpm install` in a fresh worktree before wondering why the build is red.

Nothing runs these for you (see the merge gate above): `.githooks/pre-push` is what
catches a broken suite before it leaves the machine.

If a test breaks, fix it before committing — no exceptions.

**Anything that talks to an external service gets tests for the ugly paths, not just the
happy one.** `zone_scorer.py` shipped with zero and spent its first prod cycle failing on
every call: the LLM returned 200 with `content: null` and `json.loads(None)` raised. A 200
means the server answered — nothing more. Validate the envelope before parsing, and the
fields after it: an object that parses can still carry `"estimatedImpact": null` or a
confidence of `"alto"`, and a field read with `.get()` outside a try takes the cycle down
on every warm instance that serves the cached copy (`.claude/rules/geo.md`).
