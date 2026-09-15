"""Finish-off coverage: kafka (chroma_buffer, anomaly_syncer, consumer,
dedup, dlq, producer, handlers), database connection/init_db, admin_router
leftovers, alerts/pubsub, and small RAG modules (cache, llm_client,
retriever, utils, config)."""

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.kafka


def _ctx(cur=None):
    ctx = MagicMock()
    ctx.__enter__.return_value = cur or MagicMock()
    ctx.__exit__.return_value = False
    return ctx


class TestChromaBuffer:
    def _buffer(self, ready=True):
        from backend.kafka.chroma_buffer import ChromaBuffer

        with patch.object(ChromaBuffer, "_init", lambda self: None):
            buf = ChromaBuffer()
        buf._ready = ready
        buf._collection = MagicMock()
        return buf

    def test_init_failure_disables(self):
        from backend.kafka import chroma_buffer as cb

        with patch.object(cb, "_build_chroma_client", side_effect=RuntimeError("x")):
            buf = cb.ChromaBuffer()
            assert buf._ready is False

    def test_init_embeddings_fallback(self):
        from backend.kafka import chroma_buffer as cb

        client = MagicMock()
        with (
            patch.object(cb, "_build_chroma_client", return_value=client),
            patch.object(cb, "_build_embeddings", side_effect=RuntimeError("ollama")),
        ):
            buf = cb.ChromaBuffer()
            assert buf._ready is True and buf._chunker is None

    def test_add_event_not_ready_ignored(self):
        buf = self._buffer(ready=False)
        buf.add_event(atm_id="A", text="t", timestamp="ts")
        assert buf._buffers == {}

    def test_add_event_triggers_window_flush(self):
        from backend.kafka import chroma_buffer as cb

        buf = self._buffer()
        with (
            patch.object(cb, "WINDOW_SIZE", 2),
            patch.object(buf, "_flush_atm") as flush,
        ):
            buf.add_event(atm_id="A", text="t1", timestamp="t1")
            buf.add_event(atm_id="A", text="t2", timestamp="t2")
            flush.assert_called_once_with("A")

    def test_flush_empty_noop(self):
        buf = self._buffer()
        buf._flush_atm("ghost")

    def test_flush_simple_chunking_with_metadata(self):
        buf = self._buffer()
        buf._chunker = None
        buf._buffers["ATM-1"] = [
            {"text": "err", "timestamp": "t1", "severity": "ERROR", "anomaly_tag": "A1"},
            {"text": "warn", "timestamp": "t2", "severity": "WARNING", "anomaly_tag": "A1"},
        ]
        buf._flush_atm("ATM-1")
        assert buf._collection.upsert.called
        metas = buf._collection.upsert.call_args[1]["metadatas"]
        assert metas[0]["severity"] == "ERROR"
        assert metas[0]["_anomaly_tag"] == "A1"

    def test_flush_chunker_path_and_empty(self):
        buf = self._buffer()
        doc = MagicMock()
        doc.page_content = "chunk text"
        buf._chunker = MagicMock()
        buf._chunker.create_documents.return_value = [doc]
        buf._buffers["ATM-2"] = [{"text": "x", "timestamp": "t", "severity": None, "anomaly_tag": None}]
        buf._flush_atm("ATM-2")
        assert buf._collection.upsert.called
        buf._chunker.create_documents.return_value = []
        buf._buffers["ATM-3"] = [{"text": "x", "timestamp": "t", "severity": None, "anomaly_tag": None}]
        buf._flush_atm("ATM-3")

    def test_flush_upsert_failure_swallowed(self):
        buf = self._buffer()
        buf._chunker = None
        buf._collection.upsert.side_effect = RuntimeError("chroma down")
        buf._buffers["ATM-9"] = [{"text": "x", "timestamp": "t", "severity": None, "anomaly_tag": None}]
        buf._flush_atm("ATM-9")

    def test_dominant_severity(self):
        buf = self._buffer()
        assert buf._get_dominant_severity(["INFO", "CRITICAL", "ERROR"]) == "CRITICAL"
        assert buf._get_dominant_severity(["UNKNOWN"]) is None
        assert buf._get_dominant_severity(["INFO", "UNKNOWN"]) == "INFO"
        assert buf._get_dominant_severity([]) is None

    def test_flush_all(self):
        buf = self._buffer()
        buf._chunker = None
        buf._buffers["A"] = [{"text": "x", "timestamp": "t", "severity": None, "anomaly_tag": None}]
        buf.flush_all()
        assert "A" not in buf._buffers

    def test_format_event_text(self):
        from backend.kafka.chroma_buffer import format_event_text

        assert "ATM_APP" in format_event_text(
            {"timestamp": "t", "source": "ATM_APP", "event_type": "E", "message": "m",
             "payload": {"a": 1, "b": 2}}
        )
        assert isinstance(format_event_text({}), str)
        assert "kv" not in format_event_text({"payload": "not-a-dict"})


class TestAnomalySyncerLeftovers:
    def _syncer(self):
        from backend.kafka.anomaly_syncer import AnomalySyncer

        with patch("backend.kafka.anomaly_syncer.ChromaBuffer"):
            return AnomalySyncer()

    def test_get_unsynced_with_ids_and_failure(self):
        import backend.kafka.anomaly_syncer as sync_mod

        syncer = self._syncer()
        syncer._synced_ids = {1, 2}
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"id": 3, "detected_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
             "anomaly_type": "A1", "atm_id": "ATM-1", "severity": "CRITICAL",
             "title": "t", "explanation": "e"}
        ]
        with patch.object(sync_mod, "get_cursor", return_value=_ctx(cur)):
            rows = syncer._get_unsynced_anomalies()
            assert rows[0]["id"] == 3
            assert "NOT IN" in cur.execute.call_args[0][0]
        with patch.object(sync_mod, "get_cursor", side_effect=RuntimeError("db")):
            assert syncer._get_unsynced_anomalies() == []

    def test_format_variants(self):
        syncer = self._syncer()
        base = {"anomaly_type": "A2", "atm_id": "ATM-1", "title": "t",
                "detected_at": None, "explanation": None}
        assert "ATM-1" in syncer._format_anomaly_text(dict(base))
        assert "Details" in syncer._format_anomaly_text(
            {**base, "explanation": "x" * 600})
        assert "k=v" in syncer._format_anomaly_text(
            {**base, "explanation": {"k": "v", "empty": ""}})

    def test_sync_once_states(self):
        syncer = self._syncer()
        syncer._chroma_buffer = None
        assert syncer.sync_once()["status"] == "chroma_unavailable"
        syncer._chroma_buffer = MagicMock()
        syncer._chroma_buffer._ready = False
        assert syncer.sync_once()["status"] == "chroma_unavailable"
        syncer._chroma_buffer._ready = True
        with patch.object(syncer, "_get_unsynced_anomalies", return_value=[]):
            assert syncer.sync_once()["status"] == "no_new_anomalies"

    def test_sync_once_success_and_item_failure(self):
        syncer = self._syncer()
        buf = MagicMock()
        buf._ready = True
        syncer._chroma_buffer = buf
        rows = [
            {"id": 1, "detected_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
             "anomaly_type": "A1", "atm_id": "ATM-1", "severity": "CRITICAL",
             "title": "t", "explanation": "e"},
            {"id": 2, "detected_at": None, "anomaly_type": "A2",
             "atm_id": "ATM-2", "severity": None, "title": "t2", "explanation": None},
        ]
        with patch.object(syncer, "_get_unsynced_anomalies", return_value=rows):
            out = syncer.sync_once()
            assert out == {"synced": 2, "status": "success"}
            assert syncer._synced_ids == {1, 2}
            buf.flush_all.assert_called_once()
        buf2 = MagicMock()
        buf2._ready = True
        buf2.add_event.side_effect = RuntimeError("bad row")
        syncer._chroma_buffer = buf2
        with patch.object(syncer, "_get_unsynced_anomalies", return_value=rows):
            assert syncer.sync_once()["synced"] == 0

    def test_run_loop_and_entrypoint(self):
        import backend.kafka.anomaly_syncer as sync_mod

        syncer = self._syncer()
        with (
            patch.object(syncer, "sync_once", return_value={"synced": 0}),
            patch("time.sleep", side_effect=KeyboardInterrupt),
        ):
            with pytest.raises(KeyboardInterrupt):
                syncer.run(interval=1)
        with (
            patch("backend.kafka.anomaly_syncer.ChromaBuffer"),
            patch.object(sync_mod.AnomalySyncer, "sync_once",
                         return_value={"synced": 0}),
            patch("time.sleep", side_effect=KeyboardInterrupt),
        ):
            with pytest.raises(KeyboardInterrupt):
                sync_mod.run_syncer(interval=1)


class TestConsumerHelpers:
    def test_deserialise(self):
        from backend.kafka import consumer

        assert consumer._deserialise(b'{"a": 1}') == {"a": 1}
        assert consumer._deserialise(b"\xff\xfe bad") is None
        assert consumer._deserialise(b"not json") is None

    def test_sigterm(self):
        from backend.kafka import consumer

        consumer._running = True
        consumer._handle_sigterm(15, None)
        assert consumer._running is False
        consumer._running = True

    def test_detection_lock(self):
        from backend.kafka import consumer

        with patch.object(consumer, "get_redis_client", return_value=None):
            assert consumer._acquire_detection_lock() is True
            assert consumer._release_detection_lock() is None
        client = MagicMock()
        client.set.return_value = True
        with patch.object(consumer, "get_redis_client", return_value=client):
            assert consumer._acquire_detection_lock() is True
            consumer._release_detection_lock()
            client.delete.assert_called_once()
        client2 = MagicMock()
        client2.set.return_value = None
        with patch.object(consumer, "get_redis_client", return_value=client2):
            assert consumer._acquire_detection_lock() is False
        bad = MagicMock()
        bad.set.side_effect = RuntimeError("redis")
        bad.delete.side_effect = RuntimeError("redis")
        with patch.object(consumer, "get_redis_client", return_value=bad):
            assert consumer._acquire_detection_lock() is True
            assert consumer._release_detection_lock() is None

    def test_trigger_detection(self):
        from backend.kafka import consumer

        consumer._cached_detector = None
        det = MagicMock()
        det.detect_and_save.return_value = 0
        with (
            patch("backend.src.anomaly_detection.ml.ml_detector.MLAnomalyDetector",
                  return_value=det),
            patch("backend.src.alerts.pubsub.publish_anomaly"),
        ):
            consumer._trigger_anomaly_detection()
            assert consumer._cached_detector is det
        det.detect_and_save.return_value = 2
        det._get_recent_anomalies.return_value = [{"anomaly_type": "A1"}]
        with patch("backend.src.alerts.pubsub.publish_anomaly") as pub:
            consumer._trigger_anomaly_detection()
            pub.assert_called_once()
        with patch(
            "backend.src.anomaly_detection.ml.ml_detector.MLAnomalyDetector",
            side_effect=RuntimeError("models"),
        ):
            consumer._cached_detector = None
            consumer._trigger_anomaly_detection()
        consumer._cached_detector = None

    def test_trigger_sync(self):
        from backend.kafka import consumer

        consumer._cached_syncer = None
        syncer = MagicMock()
        syncer.sync_once.return_value = {"synced": 3}
        with patch("backend.kafka.anomaly_syncer.AnomalySyncer", return_value=syncer):
            consumer._trigger_anomaly_sync()
        syncer.sync_once.return_value = {"synced": 0}
        consumer._trigger_anomaly_sync()
        with patch(
            "backend.kafka.anomaly_syncer.AnomalySyncer",
            side_effect=RuntimeError("x"),
        ):
            consumer._cached_syncer = None
            consumer._trigger_anomaly_sync()
        consumer._cached_syncer = None

    def test_health_server_oserror(self):
        from backend.kafka import consumer

        with patch("backend.kafka.consumer.HTTPServer", side_effect=OSError("busy")):
            consumer._start_health_server()

    def test_health_server_serves(self):
        from backend.kafka import consumer

        server = MagicMock()
        server.server_port = 8081
        created = {}

        class FakeServer:
            def __init__(self, addr, handler):
                created["handler"] = handler
                self.server_port = addr[1]

            def serve_forever(self):
                handler = created["handler"]
                inst = handler.__new__(handler)
                inst.path = "/health"
                inst.send_response = MagicMock()
                inst.send_header = MagicMock()
                inst.end_headers = MagicMock()
                inst.wfile = MagicMock()
                inst.do_GET()
                inst.wfile.write.assert_called_once_with(b'{"status":"ok"}')
                inst.path = "/nope"
                inst.do_GET()

        with patch("backend.kafka.consumer.HTTPServer", FakeServer):
            consumer._start_health_server()


class TestDedupDlqProducer:
    def test_deduplicator_memory(self):
        from backend.kafka.deduplicator import Deduplicator

        with patch.object(Deduplicator, "_is_redis_available", return_value=False):
            d = Deduplicator(max_size=2)
            assert d.is_duplicate("m1") is False
            d.mark_seen("m1")
            assert d.is_duplicate("m1") is True

    def test_deduplicator_redis(self):
        from backend.kafka import deduplicator as dd
        from backend.kafka.deduplicator import Deduplicator

        client = MagicMock()
        client.ping.return_value = True
        client.sismember.return_value = True
        with patch.object(dd, "get_redis_client", return_value=client):
            d = Deduplicator()
            assert d.is_duplicate("m") is True
            d.mark_seen("m")
            client.sadd.assert_called_once()
            client.expire.assert_called_once()
        with patch.object(dd, "get_redis_client", return_value=None):
            d2 = Deduplicator()
            assert d2._is_redis_available() is False
            assert d2.is_duplicate("fresh") is False

    def test_dlq(self):
        from backend.kafka import dlq

        with patch.object(dlq, "get_redis_client", return_value=None):
            assert dlq.push_to_dlq({"a": 1}, "err") is False
            assert dlq.get_dlq_length() == 0
            assert dlq.process_dlq_batch() == 0
        client = MagicMock()
        with patch.object(dlq, "get_redis_client", return_value=client):
            assert dlq.push_to_dlq({"a": 1}, "err", source="KAFKA") is True
            assert dlq.push_to_dlq("raw", "err") is True
            client.xlen.return_value = 5
            assert dlq.get_dlq_length() == 5
            client.xread.return_value = []
            assert dlq.process_dlq_batch() == 0
            client.xread.return_value = [
                ("ingestion:dlq", [
                    ("1-0", {"retry_count": "0", "status": "pending",
                             "created_at": "0"}),
                    ("1-1", {"retry_count": "9", "status": "pending",
                             "created_at": "0"}),
                    ("1-2", {"retry_count": "0", "status": "exhausted"}),
                    ("1-3", {"retry_count": "0", "status": "retrying"}),
                    ("1-4", {"retry_count": "0", "status": "pending",
                             "created_at": str(1e12)}),
                ])
            ]
            assert dlq.process_dlq_batch() == 2
        bad = MagicMock()
        bad.xadd.side_effect = RuntimeError("redis")
        bad.xlen.side_effect = RuntimeError("redis")
        bad.xread.side_effect = RuntimeError("redis")
        with patch.object(dlq, "get_redis_client", return_value=bad):
            assert dlq.push_to_dlq({}, "e") is False
            assert dlq.get_dlq_length() == 0
            assert dlq.process_dlq_batch() == 0

    def test_producer(self):
        import backend.kafka.producer as prod

        with patch("backend.kafka.producer.KafkaProducer") as kp:
            p = prod.ATMProducer()
            p.send_event({"t": 1})
            p.send_metric({"m": 1})
            p.flush()
            p.close()
            kp.assert_called()
        assert prod._serialise({"a": 1}) == json.dumps({"a": 1}).encode()
        with patch("backend.kafka.producer.KafkaProducer",
                   side_effect=RuntimeError("no kafka")):
            with pytest.raises(RuntimeError):
                prod.ATMProducer()
        with patch("backend.kafka.producer.KafkaProducer"):
            assert isinstance(prod.get_producer(), prod.ATMProducer)


class TestHandlers:
    def _msg(self, **over):
        base = {"message_id": "m1", "timestamp": "2026-01-01T12:00:00+00:00",
                "source": "ATM_APP", "severity": "ERROR", "atm_id": "ATM-1",
                "message": "boom", "payload": {"_anomaly_tag": "A1"}}
        base.update(over)
        return base

    def test_event_missing_fields(self):
        from backend.kafka.handlers import event_handler as eh

        with patch.object(eh, "_route_to_ingestion_errors") as route:
            assert eh.handle_event({"source": "X"}, MagicMock()) is False
            route.assert_called_once()

    def test_event_bad_timestamp(self):
        from backend.kafka.handlers import event_handler as eh

        with patch.object(eh, "_route_to_ingestion_errors") as route:
            assert eh.handle_event(
                self._msg(timestamp="not-a-date"), MagicMock()) is False
            route.assert_called_once()

    def test_event_db_failure(self):
        from backend.kafka.handlers import event_handler as eh

        with patch.object(eh, "get_cursor", side_effect=RuntimeError("db")):
            assert eh.handle_event(self._msg(), MagicMock()) is False

    def test_event_success_without_atm(self):
        from backend.kafka.handlers import event_handler as eh

        msg = self._msg()
        del msg["atm_id"]
        buf = MagicMock()
        with (
            patch.object(eh, "get_cursor", return_value=_ctx()),
            patch.object(eh, "increment_event_counter") as inc,
        ):
            assert eh.handle_event(msg, buf) is True
            buf.add_event.assert_not_called()
            inc.assert_called_once()

    def test_event_success_with_atm_and_dict_ts(self):
        from backend.kafka.handlers import event_handler as eh

        msg = self._msg(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        msg["payload"] = "not-a-dict"
        buf = MagicMock()
        with (
            patch.object(eh, "get_cursor", return_value=_ctx()),
            patch.object(eh, "increment_event_counter"),
            patch.object(eh, "track_unique_atm") as track,
        ):
            assert eh.handle_event(msg, buf) is True
            track.assert_called_once_with("ATM-1")

    def test_event_route_failure_swallowed(self):
        from backend.kafka.handlers import event_handler as eh

        with patch.object(eh, "get_cursor", side_effect=RuntimeError("db")):
            eh._route_to_ingestion_errors("S", "detail", "raw")

    def test_metric_paths(self):
        from backend.kafka.handlers import metric_handler as mh

        good = {"message_id": "m", "timestamp": "2026-01-01T12:00:00+00:00",
                "source": "KAFKA", "entity_id": "ATM-1", "metric_name": "cpu",
                "metric_value": 1.0}
        with patch.object(mh, "_route_to_ingestion_errors") as route:
            assert mh.handle_metric({"source": "X"}) is False
            route.assert_called_once()
        with patch.object(mh, "_route_to_ingestion_errors") as route:
            bad_num = dict(good, metric_value="not-a-number")
            assert mh.handle_metric(bad_num) is False
            route.assert_called_once()
        with patch.object(mh, "_route_to_ingestion_errors") as route:
            bad_ts = dict(good, timestamp="not-a-date")
            assert mh.handle_metric(bad_ts) is False
            route.assert_called_once()
        with patch.object(mh, "get_cursor", side_effect=RuntimeError("db")):
            assert mh.handle_metric(dict(good)) is False
        with (
            patch.object(mh, "get_cursor", return_value=_ctx()),
            patch("backend.kafka.handlers.metric_handler.increment_event_counter"),
            patch("backend.kafka.handlers.metric_handler.track_unique_atm") as track,
        ):
            assert mh.handle_metric(dict(good)) is True
            track.assert_called_once_with("ATM-1")
        with patch.object(mh, "get_cursor", side_effect=RuntimeError("db")):
            mh._route_to_ingestion_errors("S", "d", "r")


class TestConnectionInitDb:
    def test_get_conn_retries_then_raises(self):
        import psycopg2.pool

        import backend.src.database.connection as conn_mod

        pool = MagicMock()
        pool.getconn.return_value = MagicMock()
        with patch.object(conn_mod, "_get_pool", return_value=pool):
            assert conn_mod.get_conn() is pool.getconn.return_value
        failing = MagicMock()
        failing.getconn.side_effect = psycopg2.pool.PoolError("exhausted")
        with (
            patch.object(conn_mod, "_get_pool", return_value=failing),
            patch("time.sleep") as slp,
        ):
            with pytest.raises(Exception):
                conn_mod.get_conn()
            assert slp.call_count == 2

    def test_release_conn_rollback_failure(self):
        import backend.src.database.connection as conn_mod

        bad = MagicMock()
        bad.rollback.side_effect = RuntimeError("closed")
        pool = MagicMock()
        with patch.object(conn_mod, "_get_pool", return_value=pool):
            conn_mod.release_conn(bad)
            pool.putconn.assert_called_once_with(bad)

    def test_get_cursor_commit_and_rollback(self):
        import backend.src.database.connection as conn_mod

        conn = MagicMock()
        cur = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        conn.cursor.return_value = ctx
        with (
            patch.object(conn_mod, "get_conn", return_value=conn),
            patch.object(conn_mod, "release_conn"),
        ):
            with conn_mod.get_cursor(commit=True):
                pass
            conn.commit.assert_called_once()
            conn.reset_mock()
            with pytest.raises(RuntimeError):
                with conn_mod.get_cursor():
                    raise RuntimeError("boom")
            conn.rollback.assert_called_once()

    def test_seed_and_init(self):
        import backend.src.database.init_db as init_mod

        conn = MagicMock()
        cur = MagicMock()
        cur.rowcount = 3
        conn.cursor.return_value = _ctx(cur)
        init_mod.seed_atms(conn)
        cur.rowcount = 0
        init_mod.seed_atms(conn)
        init_mod.seed_default_admin(conn)
        init_mod.seed_retention_config(conn)
        with (
            patch.object(init_mod, "get_conn", return_value=conn),
            patch.object(init_mod, "release_conn"),
        ):
            init_mod.seed_atm_fleet()
            assert init_mod._read_schema("schema.sql").strip() != ""
        with (
            patch.object(init_mod, "_read_schema", return_value="SELECT 1"),
            patch.object(init_mod, "get_conn", return_value=conn),
            patch.object(init_mod, "release_conn"),
            patch("os.getenv", return_value="production"),
        ):
            assert init_mod.init_db(force=True) is False
        # CI sets LAAD_ENV=production globally; pin it here so the
        # production guard doesn't veto the force-allowed assertions.
        with (
            patch.dict(os.environ, {"LAAD_ENV": "test"}, clear=False),
            patch.object(init_mod, "_read_schema", return_value="SELECT 1"),
            patch.object(init_mod, "get_conn", return_value=conn),
            patch.object(init_mod, "release_conn"),
        ):
            assert init_mod.init_db(db_path="legacy.db") is True
            assert init_mod.init_db(force=True) is True
        bad_conn = MagicMock()
        bad_conn.cursor.side_effect = RuntimeError("db")
        with (
            patch.object(init_mod, "_read_schema", return_value="SELECT 1"),
            patch.object(init_mod, "get_conn", return_value=bad_conn),
            patch.object(init_mod, "release_conn"),
        ):
            with pytest.raises(RuntimeError):
                init_mod.init_db()


class TestAdminLeftovers:
    def _conn(self, fetch=None, fetchall=None, rowcount=1):
        cur = MagicMock()
        cur.fetchone.return_value = fetch
        cur.fetchall.return_value = fetchall or []
        cur.rowcount = rowcount
        return MagicMock(cursor=MagicMock(return_value=_ctx(cur))), cur

    def test_retention(self):
        from fastapi import HTTPException

        import backend.src.admin.admin_router as ar

        conn, _ = self._conn(fetch=None)
        with pytest.raises(HTTPException):
            ar.get_retention(conn=conn)
        conn2, _ = self._conn(fetch=(7, "2026-01-01"))
        assert ar.get_retention(conn=conn2)["retention_days"] == 7
        with pytest.raises(HTTPException):
            ar.update_retention(ar.RetentionUpdateRequest(days=2), conn=conn2)
        out = ar.update_retention(ar.RetentionUpdateRequest(days=30), conn=conn2)
        assert out["retention_days"] == 30

    def test_ingestion_errors(self):
        import backend.src.admin.admin_router as ar

        conn, _ = self._conn(fetch=(5,), fetchall=[(1, "t", "S", "d", "r")])
        out = ar.get_ingestion_errors(conn=conn)
        assert out["total"] == 5 and len(out["data"]) == 1
        conn2, _ = self._conn(rowcount=4)
        assert ar.clear_ingestion_errors(conn=conn2) == {"deleted": 4}

    def test_wipe_cleanup(self):
        import backend.src.admin.admin_router as ar

        with (
            patch("backend.src.admin.admin_router.run_wipe", return_value={"ok": 1}),
            patch("backend.src.admin.admin_router.run_cleanup", return_value={"ok": 2}),
        ):
            assert ar.trigger_wipe() == {"ok": 1}
            assert ar.trigger_cleanup() == {"ok": 2}

    def test_create_user_validations(self):
        from fastapi import HTTPException

        import backend.src.admin.admin_router as ar

        conn, _ = self._conn()
        with pytest.raises(HTTPException):
            ar.admin_create_user(
                ar.AdminCreateUserRequest(username="u", password="a",
                                         confirm_password="b"),
                conn=conn, current_user={"sub": "admin"})
        with pytest.raises(HTTPException):
            ar.admin_create_user(
                ar.AdminCreateUserRequest(username="u", password="a",
                                         confirm_password="a", role="super"),
                conn=conn, current_user={"sub": "admin"})
        with patch("bcrypt.hashpw", side_effect=RuntimeError("no bcrypt")):
            with pytest.raises(HTTPException):
                ar.admin_create_user(
                    ar.AdminCreateUserRequest(username="u", password="a",
                                             confirm_password="a"),
                    conn=conn, current_user={"sub": "admin"})

    def test_create_user_conflict(self):
        import psycopg2
        from fastapi import HTTPException

        import backend.src.admin.admin_router as ar

        conn = MagicMock()
        conn.cursor.side_effect = psycopg2.IntegrityError("dup")
        with pytest.raises(HTTPException) as exc:
            ar.admin_create_user(
                ar.AdminCreateUserRequest(username="u", password="a",
                                         confirm_password="a"),
                conn=conn, current_user={"sub": "admin"})
        assert exc.value.status_code == 409

    def test_training_task(self):
        import backend.src.admin.admin_router as ar

        tasks = MagicMock()
        out = ar.trigger_training(background_tasks=tasks)
        assert out.status == "started"
        fn = tasks.add_task.call_args[0][0]
        with patch("backend.src.anomaly_detection.ml.train.train",
                   side_effect=RuntimeError("boom")):
            fn()
        with patch("backend.src.anomaly_detection.ml.train.train") as tr:
            fn()
            tr.assert_called()


class TestPubsub:
    def test_publish(self):
        from backend.src.alerts import pubsub

        with patch.object(pubsub, "get_redis_client", return_value=None):
            assert pubsub.publish_anomaly({"anomaly_type": "A1"}) is False
        client = MagicMock()
        with patch.object(pubsub, "get_redis_client", return_value=client):
            assert pubsub.publish_anomaly(
                {"anomaly_type": "A1", "atm_id": "ATM-1"}) is True
            assert pubsub.publish_anomaly({"anomaly_type": "A1"}) is True
        bad = MagicMock()
        bad.publish.side_effect = RuntimeError("redis")
        with patch.object(pubsub, "get_redis_client", return_value=bad):
            assert pubsub.publish_anomaly({"anomaly_type": "A1"}) is False

    def test_top_atms(self):
        from backend.src.alerts import pubsub

        with patch.object(pubsub, "get_redis_client", return_value=None):
            assert pubsub.get_top_anomalous_atms() == []
        client = MagicMock()
        client.zrevrange.return_value = [("ATM-1", 3.0)]
        with patch.object(pubsub, "get_redis_client", return_value=client):
            assert pubsub.get_top_anomalous_atms() == [
                {"atm_id": "ATM-1", "count": 3}]
        bad = MagicMock()
        bad.zrevrange.side_effect = RuntimeError("redis")
        with patch.object(pubsub, "get_redis_client", return_value=bad):
            assert pubsub.get_top_anomalous_atms() == []


class TestSmallRagModules:
    def test_cache_redis_failures(self):
        from backend.src.rag import cache

        with patch.object(cache, "get_redis_client", return_value=None):
            assert cache.get_cached_response("q") is None
            assert cache.set_cached_response("q", {}) is None
        bad = MagicMock()
        bad.get.side_effect = RuntimeError("redis")
        bad.set.side_effect = RuntimeError("redis")
        with patch.object(cache, "get_redis_client", return_value=bad):
            assert cache.get_cached_response("q") is None
            assert cache.set_cached_response("q", {}) is None
        client = MagicMock()
        client.get.return_value = "not-json{"
        with patch.object(cache, "get_redis_client", return_value=client):
            assert cache.get_cached_response("q") is None
        assert len(cache.get_query_hash("  Hello ")) == 16

    def test_rate_limiter(self):
        from backend.src.rag.llm_client import RateLimiter

        rl = RateLimiter(max_requests=2, window_seconds=60)
        assert rl.is_rate_limited("k") is False
        assert rl.wait_time("k") >= 0

    def test_llm_generate_no_providers(self):
        from backend.src.rag import llm_client as llc

        client = llc.LLMClient()
        client.providers = []
        with pytest.raises(RuntimeError):
            client.generate("hello")
        assert llc.get_llm_client() is llc.get_llm_client()

    def test_llm_call_retries(self):
        from backend.src.rag import llm_client as llc

        client = llc.LLMClient()
        provider = {"model": "m", "api_key": "k", "base_url": "http://x",
                    "name": "llm"}
        with patch("requests.post", side_effect=RuntimeError("net")):
            with pytest.raises(RuntimeError):
                client._call_llm(provider, "p", None, 0.5, 10)
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "model": "m",
        }
        with patch("requests.post", return_value=resp):
            out = client._call_llm(provider, "p", "sys", 0.5, 10)
            assert out.text == "hi"
        bad_resp = MagicMock()
        bad_resp.json.return_value = {"error": {"message": "bad"}}
        with patch("requests.post", return_value=bad_resp):
            with pytest.raises(RuntimeError):
                client._call_llm(provider, "p", None, 0.5, 10)

    def test_retriever_pure_helpers(self):
        from backend.src.rag.retriever import RAGRetriever, reset_retriever

        with patch.object(RAGRetriever, "__init__", lambda self: None):
            r = RAGRetriever()
            r.collection = MagicMock()
            r.client = MagicMock()
            assert r._calculate_confidence(0.0) >= r._calculate_confidence(5.0)
            assert r._calculate_confidence(None) == 0.5
            from backend.src.rag.retriever import RetrievedChunk

            chunks = [
                RetrievedChunk(text="t", chunk_id="c", atm_id="A",
                               timestamp="2026-05-01T12:00:00+00:00",
                               distance=0.1, confidence_score=0.9),
                RetrievedChunk(text="t", chunk_id="c2", atm_id="A",
                               timestamp="not-a-date",
                               distance=0.2, confidence_score=0.8),
            ]
            assert len(r._apply_temporal_boost(chunks)) == 2
            assert r._sort_by_most_recent(chunks)[0].chunk_id == "c"
            r.collection.count.return_value = 10
            assert r.get_collection_stats()["total_chunks"] == 10
            r.collection.count.side_effect = RuntimeError("x")
            assert "error" in r.get_collection_stats()
            r.collection = None
            assert "error" in r.get_collection_stats()
            assert r.retrieve_by_atm("ATM-1") == []
            r.collection = MagicMock()
            r.client = MagicMock()
            assert r.clear_collection()["success"] is True
            assert r.rebuild_collection()["success"] is True
            r.client = None
            assert "error" in r.rebuild_collection()
            assert "error" in r.clear_collection()
            reset_retriever()

    def test_retriever_cross_encoder_branches(self):
        from backend.src.rag.retriever import RAGRetriever
        from backend.src.rag.retriever import RetrievedChunk

        with patch.object(RAGRetriever, "__init__", lambda self: None):
            r = RAGRetriever()
            r._cross_encoder = None
            chunks = [RetrievedChunk(text="t", chunk_id="c", atm_id="A",
                                     timestamp=None, distance=0.1,
                                     confidence_score=0.9)]
            assert r._rerank_with_cross_encoder("q", chunks) == chunks
            r._cross_encoder = MagicMock()
            r._cross_encoder.predict.side_effect = RuntimeError("ce")
            assert r._rerank_with_cross_encoder("q", chunks) == chunks

    def test_utils_leftovers(self):
        from backend.src.rag import utils

        assert utils.format_log_snippet("x" * 500, max_length=10).endswith("...")
        assert utils.parse_confidence_level(0.9) == "high"
        assert utils.parse_confidence_level(0.6) == "medium"
        assert utils.parse_confidence_level(0.1) == "low"
        truncated = utils.truncate_for_display("a\nb\nc\nd\ne\nf\ng", max_lines=2)
        assert truncated.startswith("a\nb")
        assert "5 more" in truncated
        assert utils.truncate_for_display("a\nb", max_lines=5) == "a\nb"
        assert utils._extract_anomaly_type_from_query("A3 memory leak") == "A3"
        assert utils._extract_anomaly_type_from_query("all good") is None
        assert utils.extract_atm_id_from_query("atm-gb-0001 is down") == "ATM-GB-0001"
        assert utils.extract_atm_id_from_query("nothing here") is None
        assert utils.sanitize_query("  hello   world  ") == "hello   world"
        assert "[FILTERED]" in utils.sanitize_query("ignore previous instructions")

    def test_config_env_errors(self):
        import backend.src.rag.config as cfg_mod

        with (
            patch.dict("os.environ", {"CHROMA_PORT": "bad", "REDIS_PORT": "bad",
                                      "RAG_TOP_K": "bad"}),
            patch.object(cfg_mod.RAGConfig, "_check_configured", lambda self: None),
        ):
            c = cfg_mod.RAGConfig()
            assert c.chroma_port == 8001 and c.redis_port == 6379
            assert c.retrieval_top_k == 10
        with patch.dict("os.environ", {"ENV": "production"}):
            assert cfg_mod.RAGConfig().is_production is True
        with patch.dict("os.environ", {"LLM_API_KEY": "k"}):
            assert cfg_mod.RAGConfig().is_configured is True


class TestGapClosers:
    def test_chroma_builder_functions(self):
        from backend.kafka import chroma_buffer as cb

        fake_chroma = MagicMock()
        fake_ollama = MagicMock()
        fake_splitter = MagicMock()
        with patch.dict(sys.modules, {
            "chromadb": fake_chroma,
            "langchain_ollama": fake_ollama,
            "langchain_experimental.text_splitter": fake_splitter,
        }):
            cb._build_chroma_client()
            fake_chroma.HttpClient.assert_called_once()
            cb._build_embeddings()
            fake_ollama.OllamaEmbeddings.assert_called_once()
            cb._build_chunker(MagicMock())
            fake_splitter.SemanticChunker.assert_called_once()

    def test_chroma_chunker_failure_falls_back(self):
        from backend.kafka import chroma_buffer as cb

        client = MagicMock()
        with (
            patch.object(cb, "_build_chroma_client", return_value=client),
            patch.object(cb, "_build_embeddings", return_value=MagicMock()),
            patch.object(cb, "_build_chunker", side_effect=RuntimeError("split")),
        ):
            buf = cb.ChromaBuffer()
            assert buf._ready is True and buf._chunker is None

    def test_chroma_flush_whitespace_only(self):
        from backend.kafka.chroma_buffer import ChromaBuffer

        with patch.object(ChromaBuffer, "_init", lambda self: None):
            buf = ChromaBuffer()
        buf._ready = True
        buf._collection = MagicMock()
        buf._chunker = None
        buf._buffers["ATM-W"] = [
            {"text": "   ", "timestamp": "t", "severity": None, "anomaly_tag": None}
        ]
        buf._flush_atm("ATM-W")
        docs = buf._collection.upsert.call_args[1]["documents"]
        assert docs == ["ATM: ATM-W |"]

    def test_syncer_init_failure_and_run_error_branch(self):
        import backend.kafka.anomaly_syncer as sync_mod

        with patch(
            "backend.kafka.anomaly_syncer.ChromaBuffer",
            side_effect=RuntimeError("no chroma"),
        ):
            syncer = sync_mod.AnomalySyncer()
            assert syncer._chroma_buffer is None
            assert syncer._synced_ids == set()
        with patch("backend.kafka.anomaly_syncer.ChromaBuffer"):
            syncer = sync_mod.AnomalySyncer()
        with (
            patch.object(syncer, "sync_once", side_effect=[RuntimeError("boom"), {"synced": 0}]),
            patch("time.sleep", side_effect=KeyboardInterrupt),
        ):
            with pytest.raises(KeyboardInterrupt):
                syncer.run(interval=1)

    def test_dedup_redis_failures_and_lru(self):
        from backend.kafka import deduplicator as dd
        from backend.kafka.deduplicator import Deduplicator

        bad_ping = MagicMock()
        bad_ping.ping.side_effect = RuntimeError("redis down")
        with patch.object(dd, "get_redis_client", return_value=bad_ping):
            d = Deduplicator()
            assert d._is_redis_available() is False
        flaky = MagicMock()
        flaky.ping.return_value = True
        flaky.sismember.side_effect = RuntimeError("read fail")
        with patch.object(dd, "get_redis_client", return_value=flaky):
            d = Deduplicator()
            assert d.is_duplicate("x") is False
        flaky2 = MagicMock()
        flaky2.ping.return_value = True
        flaky2.sadd.side_effect = RuntimeError("write fail")
        with patch.object(dd, "get_redis_client", return_value=flaky2):
            d = Deduplicator()
            d.mark_seen("x")
            assert d.is_duplicate("x") is True
        with patch.object(Deduplicator, "_is_redis_available", return_value=False):
            d = Deduplicator(max_size=2)
            d.mark_seen("a")
            d.mark_seen("a")
            d.mark_seen("b")
            d.mark_seen("c")
            assert d.is_duplicate("a") is False
            assert d.is_duplicate("c") is True

    def test_producer_message_id_and_kafka_errors(self):
        import backend.kafka.producer as prod

        with patch("backend.kafka.producer.KafkaProducer"):
            p = prod.ATMProducer()
            msg = p._add_message_id({"timestamp": datetime(2026, 1, 1), "x": 1})
            assert msg["timestamp"] == "2026-01-01T00:00:00"
            assert "message_id" in msg
            kept = p._add_message_id({"message_id": "keep"})
            assert kept["message_id"] == "keep"

        class KafkaError(Exception):
            pass

        with (
            patch("backend.kafka.producer.KafkaProducer"),
            patch.object(prod, "KafkaError", KafkaError),
        ):
            p = prod.ATMProducer()
            p._producer.send.side_effect = KafkaError("broker down")
            assert p.send_event({"a": 1}) is None
            assert p.send_metric({"m": 1}) is None

    def test_handlers_naive_timestamp_and_route_success(self):
        from backend.kafka.handlers import event_handler as eh
        from backend.kafka.handlers import metric_handler as mh

        naive_event = {"message_id": "m", "timestamp": "2026-01-01T12:00:00",
                       "source": "ATM_APP", "severity": "INFO"}
        with (
            patch.object(eh, "get_cursor", return_value=_ctx()),
            patch.object(eh, "increment_event_counter"),
        ):
            assert eh.handle_event(dict(naive_event), MagicMock()) is True
        naive_metric = {"message_id": "m", "timestamp": "2026-01-01T12:00:00",
                        "source": "KAFKA", "entity_id": "SRV-1",
                        "metric_name": "cpu", "metric_value": 1.5}
        with (
            patch.object(mh, "get_cursor", return_value=_ctx()),
            patch.object(mh, "increment_event_counter"),
        ):
            assert mh.handle_metric(dict(naive_metric)) is True
        with (
            patch.object(eh, "get_cursor", return_value=_ctx()),
            patch.object(mh, "get_cursor", return_value=_ctx()),
        ):
            eh._route_to_ingestion_errors("S", "detail", "raw")
            mh._route_to_ingestion_errors("S", "detail", "raw")

    def test_admin_create_user_success(self):
        import backend.src.admin.admin_router as ar

        cur = MagicMock()
        cur.fetchone.return_value = (42,)
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        conn = MagicMock()
        conn.cursor.return_value = ctx
        out = ar.admin_create_user(
            ar.AdminCreateUserRequest(username="bob", password="pw123456",
                                     confirm_password="pw123456", role="user"),
            conn=conn, current_user={"sub": "admin"})
        assert out == {"id": 42, "username": "bob", "role": "user"}
        conn.commit.assert_called_once()

    def test_cache_hit_and_config_unconfigured(self):
        import json as _json

        from backend.src.rag import cache
        import backend.src.rag.config as cfg_mod

        client = MagicMock()
        client.get.return_value = _json.dumps({"answer": "cached!"})
        with patch.object(cache, "get_redis_client", return_value=client):
            assert cache.get_cached_response("q") == {"answer": "cached!"}
            cache.set_cached_response("q", {"answer": "cached!"})
            client.set.assert_called_once()
        miss_client = MagicMock()
        miss_client.get.return_value = None
        with patch.object(cache, "get_redis_client", return_value=miss_client):
            assert cache.get_cached_response("nope") is None
        env = {k: v for k, v in os.environ.items()
               if k not in ("LLM_API_KEY", "WANDB_API_KEY")}
        with patch.dict("os.environ", env, clear=True):
            c = cfg_mod.RAGConfig()
            assert c.is_configured is False

    def test_utils_classify_and_extract_variants(self):
        from backend.src.rag import utils

        assert utils.classify_query_type("how to fix the dispenser") == utils.QueryType.TROUBLESHOOTING
        assert utils.classify_query_type("why is ATM-1 down?") == utils.QueryType.DIAGNOSTIC
        assert utils.extract_atm_id_from_query("ATM 1 is down") == "ATM-GB-0001"
        assert utils.extract_atm_id_from_query("check ATM-0002 please") == "ATM-GB-0002"
        assert utils._extract_anomaly_type_from_query("network timeout storm") == "A1"
        assert utils._extract_anomaly_type_from_query("malformed payloads") == "A7"
        assert "  " not in utils.format_log_snippet("short", max_length=200)

    def test_init_db_seeds_existing_admin(self):
        import backend.src.database.init_db as init_mod

        conn = MagicMock()
        cur = MagicMock()
        cur.rowcount = 5
        conn.cursor.return_value = _ctx(cur)
        init_mod.seed_default_admin(conn)
        cur.rowcount = 0
        init_mod.seed_default_admin(conn)

    def test_retrieve_filters_boost_sort_and_errors(self):
        from backend.src.rag.retriever import RAGRetriever

        def located(**attrs):
            with patch.object(RAGRetriever, "__init__", lambda self: None):
                r = RAGRetriever()
            for k, v in attrs.items():
                setattr(r, k, v)
            return r

        payload = {
            "documents": [["doc one", "doc two"]],
            "ids": [["id1"]],
            "distances": [[0.2, 0.4]],
            "metadatas": [[{"atm_id": "ATM-1", "last_timestamp": "2020-01-01T00:00:00+00:00"},
                           {"atm_id": "ATM-2", "last_timestamp": "2020-01-02T00:00:00+00:00"}]],
        }
        r = located(collection=MagicMock(), client=MagicMock(), _cross_encoder=None)
        r.collection.query.return_value = payload
        with patch.object(RAGRetriever, "_load_cross_encoder", lambda self: None):
            chunks = r.retrieve("q", atm_id="ATM-1", anomaly_type="A7", top_k=2,
                                temporal_boost=False, error_only=True,
                                most_recent_first=True)
        assert [c.chunk_id for c in chunks] == ["chunk_1", "id1"]
        where = r.collection.query.call_args[1]["where"]
        assert where["$and"][0] == {"atm_id": "ATM-1"}

        r2 = located(collection=MagicMock(), client=MagicMock(), _cross_encoder=None)
        r2.collection.query.return_value = payload
        with patch.object(RAGRetriever, "_load_cross_encoder", lambda self: None):
            chunks = r2.retrieve("q", anomaly_type="A1", top_k=1)
        assert len(chunks) == 1

        r3 = located(collection=None, client=None, _cross_encoder=None)
        assert r3.retrieve("q") == []

        r4 = located(collection=MagicMock(), client=MagicMock(), _cross_encoder=None)
        r4.collection.query.side_effect = RuntimeError("chroma down")
        assert r4.retrieve("q") == []

        r5 = located(collection=MagicMock(), client=MagicMock(), _cross_encoder=None)
        r5.collection.query.return_value = {"documents": []}
        with patch.object(RAGRetriever, "_load_cross_encoder", lambda self: None):
            assert r5.retrieve("q", top_k=5) == []

    def test_retrieve_by_atm_and_collection_helpers(self):
        from backend.src.rag.retriever import RAGRetriever, get_retriever

        with patch.object(RAGRetriever, "__init__", lambda self: None):
            r = RAGRetriever()
            r.collection = None
            r.client = None
            assert r.retrieve_by_atm("ATM-1") == []
            r.collection = MagicMock()
            r.collection.get.return_value = {
                "documents": ["d1"], "metadatas": [{"last_timestamp": "t"}],
                "ids": ["i1"],
            }
            chunks = r.retrieve_by_atm("ATM-1")
            assert chunks[0].chunk_id == "i1"
            r.collection.get.side_effect = RuntimeError("x")
            assert r.retrieve_by_atm("ATM-1") == []
            r.collection = MagicMock()
            r.collection.get.return_value = {"documents": [], "metadatas": []}
            assert r.retrieve_by_atm("ATM-1") == []
        with patch.object(RAGRetriever, "__init__", lambda self: None):
            r = RAGRetriever()
            r._cross_encoder = None
            r.client = MagicMock()
            r.collection = MagicMock()
            with patch("backend.src.rag.retriever._HAS_CROSS_ENCODER", False):
                r._load_cross_encoder()
                assert r._cross_encoder is None
        import backend.src.rag.retriever as ret_mod
        with patch.object(ret_mod, "_retriever", None):
            with patch.object(RAGRetriever, "__init__", lambda self: None):
                inst = get_retriever()
                assert isinstance(inst, RAGRetriever)
