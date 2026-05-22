# API Reference

31+ endpoints across 8 routers. All endpoints return JSON. Authenticated endpoints require `Authorization: Bearer <jwt>` header.

## Authentication — `/api/auth`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | None | Validate credentials (OAuth2PasswordRequestForm), issue JWT (8h expiry, HS256) |
| GET | `/auth/me` | JWT | Return current user profile |
| POST | `/auth/logout` | JWT | Revoke current JWT via Redis blacklist (secure logout) |
| POST | `/auth/register` | None | Register new user account |

bcrypt password hashing, 2 roles (`admin`, `user`), `require_admin` dependency guard for admin endpoints. JWT tokens are blacklisted in Redis on logout — revoked tokens are rejected even if not yet expired.

## Anomalies — `/api/anomalies`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/anomalies` | JWT | Paginated, filterable list. Supports `group_by`: `atm`, `atm_anomaly`, `title_atm`. Supports `sort_by`, `detection_source`, `is_starred` |
| PATCH | `/{anomalyId}/resolve` | JWT | Toggle active/inactive |
| PATCH | `/{anomalyId}/star` | JWT | Toggle starred/unstarred |
| PATCH | `/{anomalyId}/feedback` | JWT | Submit feedback (LIKE/DISLIKE false positive tracking) |

### Query parameters for `GET /anomalies`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `sort_by` | string | `score` | Sort order: `score` (criticality), `detected_at` (most recent), `severity` |
| `limit` | int | 500 | Max results (max 2000) |
| `detection_source` | string | - | Filter by source: `ML_ENSEMBLE`, `ZSCORE`, `HEURISTIC` |
| `is_starred` | int | - | Filter by starred state: `1` = starred, `0` = unstarred |
| `atm_id` | string | - | Filter by ATM ID |
| `severity` | string | - | Filter by severity: `CRITICAL`, `HIGH`, `MAJOR`, `LOW` |
| `anomaly_type` | string | - | Filter by type: `A1`–`A7`, `UNKNOWN` |
| `entity_type` | string | - | `atm` or `server` |

## Analysis — `/api/analysis`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/analysis/detailed` | JWT | Ranked anomaly list with `root_cause`, `operations`, `recommended_action`. Optional `Anomaly` query param |
| GET | `/analysis/metrics` | JWT | Time-bucketed anomaly counts + summary stats. Params: `hours`, `bucket_minutes`, `anomaly_type`, `severity`, `is_active` |

## Admin — `/api/admin`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/admin/retention` | Admin JWT | Get current retention period |
| PUT | `/admin/retention` | Admin JWT | Set retention period (1–365 days) |
| POST | `/admin/cleanup/run` | Admin JWT | Manually trigger retention cleanup (batched DELETE 5,000/batch + VACUUM) |
| POST | `/admin/cleanup/wipe` | Admin JWT | Wipe all data |
| POST | `/admin/users` | Admin JWT | Create user |

## RAG — `/api/rag`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/rag/query` | JWT | Query with automatic routing (stats→DB, others→LLM), rate limited 10 req/min |
| GET | `/api/rag/anomalies/stats` | JWT | Direct anomaly statistics (bypasses LLM, returns DB counts) |
| POST | `/api/rag/feedback` | JWT | Submit feedback (helpful/not_helpful/uncertain) |
| GET | `/api/rag/history` | JWT | Query history (paginated, limit/offset) |
| GET | `/api/rag/stats` | JWT | Collection chunks, total queries |
| POST | `/api/rag/recalibrate` | Admin JWT | Manual recalibration trigger |

## Analytics — `/api/analytics`

| Method | Endpoint | Parameters | Description |
|---|---|---|---|
| GET | `/api/analytics/stats/realtime` | `hours` (0 = all time) | Real-time stats from Redis (events by source, anomaly types, unique ATMs) |
| GET | `/api/analytics/events` | `hours`, `bucket_minutes`, `sources` | Time-bucketed event counts with anomaly markers |
| GET | `/api/analytics/metrics` | `hours`, `bucket_minutes`, `sources` | Time-bucketed metric averages with anomaly markers |
| GET | `/api/analytics/metrics/list` | None | List of all unique metric names in the database |
| GET | `/api/analytics/entities` | None | All 13 entities with `atm_id`, `os_version`, `location_code` |

## Events — `/api/events`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/events` | JWT | Paginated event list |
| GET | `/events/stats` | JWT | Event statistics |

## Metrics — `/api/metrics`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/metrics` | JWT | Paginated metric list |

## Health

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Server health check |
| GET | `/health/ready` | None | Readiness probe (DB connectivity) |
