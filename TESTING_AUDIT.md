# LAAD Testing Coverage Audit

**Current**: 921 tests (655 backend pytest + 181 frontend vitest + 10 Playwright E2E + 75 Terraform assertions)
**Target**: ~1,015 tests across 6 layers
**Progress**: ✅ Phase 4 complete (9 per-module Terraform tests + checkov inline skips)

---

## The Plan

### ✅ Phase 1: Critical Backend Gaps — **IMPLEMENTED** (+58 new, 76 total with pre-existing)

| File | What | Type | Tests | Status |
|------|------|------|-------|--------|
| `backend/tests/test_pubsub_alerts.py` | Redis Pub/Sub alerting | Unit + mock Redis | 7 | ✅ Pre-existing |
| `backend/tests/test_analytics_counters.py` | Analytics helpers (counters, HLL, realtime) | Unit + mock Redis | 11 | ✅ Pre-existing |
| `backend/tests/test_server_routes.py` | Health probes, startup retry, exception handler, CORS | Integration + TestClient | 12 | ⏳ Written — awaiting CI |
| `backend/tests/test_analytics_router_endpoints.py` | Analytics endpoint integration via TestClient | Integration + TestClient | 9 | ⏳ Written — awaiting CI |
| `backend/tests/test_analysis_router_full.py` | `/analysis/detailed` + `/analysis/metrics` endpoints | Integration + TestClient | 5 | ⏳ Written — awaiting CI |
| `backend/tests/test_parsers_edge_cases.py` | 8 parsers × edge cases (malformed, missing, boundary) | Unit + parametrize | 32 | ⏳ Written — awaiting CI |

### ✅ Phase 2: Under-Tested Backend — **IMPLEMENTED** (+52 new, +29 pre-existing analysis)

| File | What | Type | Tests | Status |
|------|------|------|-------|--------|
| `backend/tests/test_anomalies_router_full.py` | Feedback PATCH, 3 grouping modes, 3 sort modes, 6 filters, cache, pagination, auth | Integration | 20 | ✅ New |
| `backend/tests/test_admin_router_full.py` | Ingestion-errors CRUD, cleanup triggers, user create + validation | Integration | 10 | ✅ New |
| `backend/tests/test_cleanup_direct.py` | `batched_delete()`, `batched_delete_all()`, `run_wipe()` — edge cases | Unit + mock conn | 9 | ✅ New |
| `backend/tests/test_write_helper_retry.py` | Retry/backoff, execute_values vs executemany, transient errors | Unit + mock conn | 6 | ✅ New |
| `backend/tests/test_continuous_generator.py` | `emit_tick()`, anomaly cooldown, backfill, producer flush | Unit + mock producer | 7 | ✅ New |
| `backend/tests/test_analysis_logic.py` | A1–A7 functions, `_build_classifier_description()`, `build_detailed_table()`, `time_window()`, `rank_algorithm()` | Unit | 29 | ✅ Pre-existing (comprehensive) |
| `backend/tests/test_anomalies_endpoints.py` | Basic list/filter/resolve/star/feedback | Integration | 3 | ✅ Pre-existing |
| `backend/tests/test_admin_retention_endpoints.py` | Retention GET/PUT, admin-only check, wipe | Integration | 2 | ✅ Pre-existing |
| `backend/tests/test_admin_training_endpoint.py` | ML training route check, method, response model | Unit | 3 | ✅ Pre-existing |
| `backend/tests/test_cleanup.py` | run_cleanup, defaults, batched_delete batches | Integration | 3 | ✅ Pre-existing |

### ✅ Phase 3: Frontend Coverage — **IMPLEMENTED** (+32 new, 4 new/2 enhanced files)

| File | What | Type | Tests | Status |
|------|------|------|-------|--------|
| `frontend/src/test/App.test.jsx` | Auth routing, login page, dashboard, admin page | Integration + mocked context | 4 | ✅ New |
| `frontend/src/test/DiagnosticAssistant.test.jsx` | Chat UI, tabs, new chat, example queries, input field, loading indicator, history tab | Component + mocked context | 8 | ✅ Enhanced |
| `frontend/src/test/AdminSettings.test.jsx` | Page title, sections, loading state, no-errors state, save/cleanup buttons, create user form | Component + mocked auth | 6 | ✅ Enhanced |
| `frontend/src/test/AnomalyListPage.test.jsx` | Title/subtitle, empty state, filter controls, data rendering, auth error, severity badges | Component + mocked fetch | 6 | ✅ Enhanced |
| `frontend/src/test/Analytics.test.jsx` | Page title, stats section, loading skeletons, fetch error handling | Component + mocked fetch | 4 | ✅ Enhanced |
| `frontend/src/test/AnomalyData.test.jsx` | Details loading, skeleton, star/complete buttons, empty data handling | Component + mocked fetch | 4 | ✅ Enhanced |

### ✅ Phase 4: Terraform Tests — **IMPLEMENTED** (+75 assertions + checkov inline skips across 9 modules)

| Module | Assertions | Runs | Result |
|--------|-----------|------|--------|
| VPC | 12 | 3 (plan, apply, overrides) | ✅ |
| ECR | 7 | 3 | ✅ |
| Secrets | 10 | 3 | ✅ |
| Monitoring | 6 | 3 | ✅ |
| Kafka | 8 | 3 | ✅ |
| RDS | 8 | 3 | ✅ |
| IAM | 8 | 3 | ✅ |
| ECS | 8 | 3 | ✅ |
| Frontend | 8 | 3 | ✅ |
| **Total** | **75** | **27 runs** | **✅ All pass** |

**Infrastructure:**
- 9 wrapper `main.tf` files in `terraform/tests/modules/<name>_test/main.tf`, each re-exposing its module's outputs
- 9 `.tftest.hcl` files with `mock_provider` blocks, `mock_resource.defaults`, and `mock_data` for `aws_iam_policy_document`
- `.checkov.baseline` (387 lines) deleted; inline skips added to: `ecs`, `frontend`, `iam`, `kafka`, `rds`, `secrets`, `vpc`, `sagemaker`, `monitoring`
- Old aggregate `terraform/tests/*.tftest.hcl` and `setup.tf` removed — only isolated wrapper directories remain

**Key patterns & constraints:**
- **Isolated wrapper directories > aggregate root tests** — each `terraform/tests/modules/<name>_test/` is its own root module. Eliminates cascading failures across 118 resources from 9 modules.
- **`command = plan` for variable assertions** + **`command = apply` for output assertions** — variables are always known during plan; module outputs only resolve during mock apply (because `mock_resource.defaults` values are ignored during plan phase).
- **`mock_data "aws_iam_policy_document"` requires raw JSON strings**, not `jsonencode()` — the function produces a string the AWS provider rejects as "not a JSON object".
- **Mock ARN defaults must match `arn:aws:...` pattern** — AWS provider validates ARN format during apply even with mocked resources.
- **Mock providers needed for both `hashicorp/aws` and `hashicorp/random`** (RDS uses `random_password`).
- Each test file has 3 run blocks: `test_*_variables_plan` (variable defaults), `test_*_outputs_apply` (module outputs), `test_*_variable_overrides` (custom variable values).
- Tests run via `terraform init && terraform test -verbose` from each wrapper directory independently.

### ✅ Phase 5: E2E + API Contracts — **IMPLEMENTED** (41 tests)

| File | Tool | What | Tests |
|------|------|------|-------|
| `frontend/e2e/auth.spec.js` | Playwright | Login → dashboard loads + invalid creds | 2 |
| `frontend/e2e/anomalies.spec.js` | Playwright | List loads, filter severity, toggle star | 3 |
| `frontend/e2e/diagnostic.spec.js` | Playwright | Chat interface renders, example queries visible | 1 |
| `frontend/e2e/admin.spec.js` | Playwright | Settings page loads with retention + user creation | 1 |
| `frontend/e2e/mobile.spec.js` | Playwright | Mobile + tablet viewport, sidebar collapse | 3 |
| `backend/tests/test_api_contract.py` | pytest + TestClient | Schema validation, non-5xx for all endpoints, response shape | 31 |

**Infrastructure also created:**
- `frontend/playwright.config.js` — Chromium project, 30s timeout, CI retries
- `docker-compose.yml` — `playwright` service (profile: `test`, `mcr.microsoft.com/playwright` image)
- `Makefile` — `test-e2e` (starts full stack) + `test-e2e-quick` (existing stack)
- `.github/workflows/ci.yml` — E2E job (starts Postgres, backend, frontend build, runs Playwright)
- `.gitignore` — Playwright report/results dirs added
- `frontend/package.json` — `test:e2e` script added
- Backend API contract uses `fastapi.testclient.TestClient` (no extra deps needed)

### Phase 6: Load + Security (33 tests, 8h)

| File | Tool | What | Tests |
|------|------|------|-------|
| `backend/tests/stress/test_kafka_throughput.py` | pytest + k6 | 1,000+ msg/s throughput | 2 |
| `backend/tests/stress/test_api_concurrent.py` | pytest + k6 | 100+ concurrent users | 3 |
| `backend/tests/test_security_sql_injection.py` | pytest parametrize | SQLi on all query params | 10 |
| `backend/tests/test_security_auth.py` | pytest | JWT tampering, RBAC escalation, rate-limit abuse | 13 |
| — | CI check + checkov | IaC compliance, no new findings | 5 |

### CI Gating

| Pipeline | Gate |
|----------|------|
| **pytest** | All pass + `--cov-fail-under=80` |
| **vitest** | All pass + `--coverage 80%` |
| **Playwright** | All pass — CI runs on backend + frontend changes |
| **k6** | Thresholds met (nightly + pre-release) |
| **Terraform test** | All modules pass (PR touches `terraform/`) |
| **checkov** | Zero new failures (PR touches `terraform/`) |
| **OpenAPI contract** | All 30+ endpoints match schema — CI-ready |

### Quick Wins (In Priority Order)

1. **`test_pubsub.py`** — 7 unit tests, ~30 min. Zero → ~85%.
2. **`test_analytics_router.py`** — 14 integration tests, ~2h. Zero → fully covered.
3. **`test_parsers_edge_cases.py`** — 24 unit tests, ~1.5h. ~15% → ~70%.
4. **`test_server_routes.py`** — 8 tests, ~1h. Zero → ~75%.
5. ~~**Terraform test per module** — 75 assertions across 9 modules, ~4h. Zero → comprehensive.~~ ✅ **Done**
6. ~~**Playwright E2E** — 10 tests, ~4h. Zero → first E2E coverage.~~ ✅ **Done**
