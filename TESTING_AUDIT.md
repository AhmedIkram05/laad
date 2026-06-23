# LAAD Testing Coverage Audit

**Current**: 663 tests (514 backend pytest + 149 frontend vitest)
**Target**: ~1,015 tests across 6 layers
**Delta**: +350 tests (~56h)

---

## The Plan

### Phase 1: Critical Backend Gaps (58 tests, 10h)

| File | What | Type | Tests |
|------|------|------|-------|
| `backend/tests/test_pubsub.py` | Redis Pub/Sub alerting — zero coverage | Unit + mock Redis | 7 |
| `backend/tests/test_server_routes.py` | Health probes, startup retry, lifespan, exception handler — zero coverage | Integration + TestClient | 8 |
| `backend/tests/test_analytics_router.py` | 5 analytics endpoints + 4 helpers — zero coverage | Integration + TestClient | 14 |
| `backend/tests/test_analysis_router_full.py` | `/analysis/metrics` endpoint | Integration | 4 |
| `backend/tests/test_parsers_edge_cases.py` | 8 parsers × 3 edge cases (malformed, missing fields, boundary) | Unit + parametrize | 24 |

### Phase 2: Under-Tested Backend (62 tests, 12h)

| File | What | Type | Tests |
|------|------|------|-------|
| `backend/tests/test_anomalies_router_full.py` | Feedback PATCH, 3 grouping modes, 2 filters, 3 sort modes, cache | Integration + Unit | 18 |
| `backend/tests/test_admin_router_full.py` | Ingestion-errors CRUD, cleanup/run, users create | Integration | 8 |
| `backend/tests/test_cleanup_direct.py` | `batched_delete()`, `batched_delete_all()` — no direct tests | Unit + mock conn | 8 |
| `backend/tests/test_write_helper_retry.py` | Retry/backoff, execute_values vs executemany, transient errors | Unit + mock conn | 6 |
| `backend/tests/test_analysis_detail.py` | A1–A7 functions, `_build_classifier_description()`, `build_detailed_table()`, `time_window()` | Unit | 16 |
| `backend/tests/test_continuous_generator.py` | `emit_tick()`, `backfill()` error handling, `main()` | Unit + mock producer | 6 |

### Phase 3: Frontend Coverage (32 tests, 8h)

| File | Current | Target | Tests |
|------|---------|--------|-------|
| `frontend/src/test/App.test.jsx` | 0% | 85%+ | 4 |
| `frontend/src/test/DiagnosticAssistant.test.jsx` | 21% | 80%+ | 8 |
| `frontend/src/test/AdminSettings.test.jsx` | 34% | 80%+ | 6 |
| `frontend/src/test/AnomalyListPage.test.jsx` | 44% | 80%+ | 6 |
| `frontend/src/test/Analytics.test.jsx` | 52% | 80%+ | 4 |
| `frontend/src/test/AnomalyData.test.jsx` | 59% | 80%+ | 4 |

### Phase 4: Terraform Tests (35 tests, 8h)

| File | What | Tests |
|------|------|-------|
| `terraform/tests/setup.tf` | Shared test infrastructure | — |
| `terraform/tests/vpc_test.tftest.hcl` | VPC module output assertions | 3 |
| `terraform/tests/rds_test.tftest.hcl` | RDS module output assertions | 3 |
| `terraform/tests/ecs_test.tftest.hcl` | ECS module output assertions | 3 |
| `terraform/tests/iam_test.tftest.hcl` | IAM module policy assertions | 3 |
| `terraform/tests/kafka_test.tftest.hcl` | MSK config assertions | 3 |
| `terraform/tests/ecr_test.tftest.hcl` | ECR repo assertions | 2 |
| `terraform/tests/frontend_test.tftest.hcl` | CloudFront/S3 assertions | 3 |
| — | Replace .checkov.baseline with per-finding waivers | 15 rules |

### Phase 5: E2E + API Contracts (40 tests, 10h)

| File | Tool | What | Tests |
|------|------|------|-------|
| `frontend/e2e/auth.spec.js` | Playwright | Login → dashboard loads | 2 |
| `frontend/e2e/anomalies.spec.js` | Playwright | Filter → view → resolve/star | 3 |
| `frontend/e2e/diagnostic.spec.js` | Playwright | RAG query → answer | 1 |
| `frontend/e2e/admin.spec.js` | Playwright | Retention → cleanup | 1 |
| `frontend/e2e/mobile.spec.js` | Playwright | Responsive layout | 3 |
| `backend/tests/test_api_contract.py` | pytest + openapi-core | 30+ endpoint schema validation | 30 |

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
| **Playwright** | All pass |
| **k6** | Thresholds met (nightly + pre-release) |
| **Terraform test** | All modules pass (PR touches `terraform/`) |
| **checkov** | Zero new failures (PR touches `terraform/`) |
| **OpenAPI contract** | All 30+ endpoints match schema |

### Quick Wins (In Priority Order)

1. **`test_pubsub.py`** — 7 unit tests, ~30 min. Zero → ~85%.
2. **`test_analytics_router.py`** — 14 integration tests, ~2h. Zero → fully covered.
3. **`test_parsers_edge_cases.py`** — 24 unit tests, ~1.5h. ~15% → ~70%.
4. **`test_server_routes.py`** — 8 tests, ~1h. Zero → ~75%.
5. **Terraform test per module** — 20 tests, ~4h. Zero → comprehensive.
6. **Playwright E2E** — 10 tests, ~4h. Zero → first E2E coverage.
