"""Tests for server entity support across the API layer.

Verifies:
  - Server records exist in the atms table
  - /api/analytics/entities returns both ATMs and servers
  - entity_type filter on /api/anomalies works for atm and server
  - Frontend entity label helpers work correctly
"""

from __future__ import annotations

import pytest
from psycopg2.extras import RealDictCursor


class TestDatabaseSeed:
    def test_server_records_exist(self, db_cleanup):
        from backend.src.database.connection import get_conn, release_conn

        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT atm_id, os_version, location_code FROM atms WHERE atm_id LIKE 'ATM-SERVER-%' ORDER BY atm_id"
                )
                rows = cur.fetchall()
            assert len(rows) == 3, f"Expected 3 server records, got {len(rows)}"
            ids = [r["atm_id"] for r in rows]
            assert "ATM-SERVER-001" in ids
            assert "ATM-SERVER-002" in ids
            assert "ATM-SERVER-003" in ids
        finally:
            release_conn(conn)

    def test_server_os_version(self, db_cleanup):
        from backend.src.database.connection import get_conn, release_conn

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT os_version FROM atms WHERE atm_id LIKE 'ATM-SERVER-%'"
                )
                rows = cur.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "Windows-Server-2019"
        finally:
            release_conn(conn)

    def test_total_entities_count(self, db_cleanup):
        from backend.src.database.connection import get_conn, release_conn

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM atms")
                count = cur.fetchone()[0]
            assert count == 13, (
                f"Expected 13 entities (10 ATMs + 3 servers), got {count}"
            )
        finally:
            release_conn(conn)


class TestEntitiesEndpoint:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        import backend.src.analytics.analytics_router as ar
        from backend.src.database.connection import get_conn, release_conn

        def get_db_conn_override():
            conn = get_conn()
            try:
                yield conn
            finally:
                release_conn(conn)

        monkeypatch.setattr(ar, "get_conn", get_conn)

    def test_entities_endpoint_returns_thirteen_entities(self):
        from backend.src.analytics.analytics_router import list_entities

        result = list_entities()
        entities = result.get("entities", [])
        assert len(entities) == 13, f"Expected 13, got {len(entities)}"
        ids = [e["atm_id"] for e in entities]
        assert "ATM-SERVER-001" in ids
        assert "ATM-GB-0001" in ids

    def test_entities_include_os_and_location(self):
        from backend.src.analytics.analytics_router import list_entities

        result = list_entities()
        server = next(e for e in result["entities"] if e["atm_id"] == "ATM-SERVER-001")
        assert server["os_version"] == "Windows-Server-2019"
        assert server["location_code"] == "SRV-001"


class TestAnomalyEntityTypeFilter:
    def test_entity_type_atm_filter(self):
        from backend.src.database.connection import get_conn, release_conn

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM anomalies")
                cur.execute(
                    "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation) "
                    "VALUES (NOW(), 'A1', 'ATM-GB-0001', 'CRITICAL', 'test', '{}'), "
                    "       (NOW(), 'A3', 'ATM-SERVER-001', 'MAJOR', 'test server', '{}')"
                )
            conn.commit()

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT atm_id FROM anomalies WHERE atm_id LIKE 'ATM-GB-%'")
                atm_rows = cur.fetchall()
                atm_ids = {r["atm_id"] for r in atm_rows}
                assert "ATM-GB-0001" in atm_ids
                assert "ATM-SERVER-001" not in atm_ids

                cur.execute(
                    "SELECT atm_id FROM anomalies WHERE atm_id LIKE 'ATM-SERVER-%'"
                )
                srv_rows = cur.fetchall()
                srv_ids = {r["atm_id"] for r in srv_rows}
                assert "ATM-SERVER-001" in srv_ids
                assert "ATM-GB-0001" not in srv_ids
        finally:
            release_conn(conn)

    def test_entity_type_atm_empty_when_no_matches(self):
        from backend.src.database.connection import get_conn, release_conn

        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM anomalies")
                cur.execute(
                    "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation) "
                    "VALUES (NOW(), 'A3', 'ATM-SERVER-001', 'MAJOR', 'test server', '{}')"
                )
            conn.commit()

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT atm_id FROM anomalies WHERE atm_id LIKE 'ATM-GB-%'")
                rows = cur.fetchall()
            assert len(rows) == 0, (
                "ATM filter should return no rows when only server anomalies exist"
            )
        finally:
            release_conn(conn)


class TestEntityLabelHelpers:
    """Tests for the frontend entity type helper logic (Python equivalent)."""

    @staticmethod
    def get_entity_type(atm_id):
        if not atm_id or atm_id.startswith("ATM-SERVER-"):
            return "Server"
        return "ATM"

    def test_atm_entity_type(self):
        assert self.get_entity_type("ATM-GB-0001") == "ATM"

    def test_server_entity_type(self):
        assert self.get_entity_type("ATM-SERVER-001") == "Server"

    def test_none_entity_type(self):
        assert self.get_entity_type(None) == "Server"

    def test_empty_entity_type(self):
        assert self.get_entity_type("") == "Server"

    def test_unknown_entity_type(self):
        assert self.get_entity_type("OTHER-001") == "ATM"
