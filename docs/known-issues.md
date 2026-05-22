# Known Issues

> This file tracks historical issues that have been fixed.

## Detector attribute missing in Kafka consumer — **FIXED** (May 2026)

**Historical issue:** `consumer.py:83` called `_cached_detector._get_recent_anomalies(n)` but `MLAnomalyDetector` had no such method.

**Impact:** Pub/Sub anomaly publishing failed silently — anomalies were still saved to DB and appeared in the dashboard on next refresh. This only affected the real-time Pub/Sub streaming path; no data loss occurred.

**Fix:** Added `_get_recent_anomalies(n)` method to `MLAnomalyDetector` and tracking of saved anomalies during detection:
- `ml_detector.py:198`: Added `self._last_saved_anomalies: list[dict] = []`
- `ml_detector.py:204`: Cleared at start of `detect_and_save()`
- `ml_detector.py:424-438`: Track anomalies in `_save_anomaly()` after INSERT
- `ml_detector.py:663-682`: Added `_get_recent_anomalies(n)` method returning last N anomalies

**Result:** Anomalies are now published to Redis Pub/Sub in real-time for live dashboard streaming.
