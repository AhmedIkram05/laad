"""Tests for Redis Pub/Sub anomaly alerting."""

import pytest
from unittest.mock import MagicMock, patch


class TestPubSubAlerts:
    """Test cases for Redis Pub/Sub anomaly publishing."""

    @patch("backend.src.alerts.pubsub.get_redis_client")
    def test_publish_anomaly_succeeds(self, mock_get_client):
        """Test that anomaly is published to Redis Pub/Sub."""
        from backend.src.alerts.pubsub import publish_anomaly

        mock_client = MagicMock()
        mock_client.publish.return_value = 1
        mock_get_client.return_value = mock_client

        anomaly_data = {
            "anomaly_type": "A1",
            "atm_id": "ATM-GB-0001",
            "severity": "CRITICAL",
            "title": "ATM offline",
        }

        result = publish_anomaly(anomaly_data)

        assert result is True
        mock_client.publish.assert_called_once()
        mock_client.zincrby.assert_called_once_with("stats:atm:rank", 1, "ATM-GB-0001")

    @patch("backend.src.alerts.pubsub.get_redis_client")
    def test_publish_anomaly_returns_false_when_redis_down(self, mock_get_client):
        """Test that publish returns False when Redis is unavailable."""
        from backend.src.alerts.pubsub import publish_anomaly

        mock_get_client.return_value = None

        result = publish_anomaly({"anomaly_type": "A1"})

        assert result is False

    @patch("backend.src.alerts.pubsub.get_redis_client")
    def test_publish_anomaly_handles_error(self, mock_get_client):
        """Test that publish handles Redis errors gracefully."""
        from backend.src.alerts.pubsub import publish_anomaly

        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception("Pub/Sub error")
        mock_get_client.return_value = mock_client

        result = publish_anomaly({"anomaly_type": "A1"})

        assert result is False

    @patch("backend.src.alerts.pubsub.get_redis_client")
    def test_publish_anomaly_without_atm_id(self, mock_get_client):
        """Test that publish works when anomaly has no atm_id."""
        from backend.src.alerts.pubsub import publish_anomaly

        mock_client = MagicMock()
        mock_client.publish.return_value = 1
        mock_get_client.return_value = mock_client

        result = publish_anomaly({"anomaly_type": "A7", "severity": "HIGH"})

        assert result is True
        mock_client.zincrby.assert_not_called()

    @patch("backend.src.alerts.pubsub.get_redis_client")
    def test_get_top_anomalous_atms(self, mock_get_client):
        """Test that top anomalous ATMs are retrieved from sorted set."""
        from backend.src.alerts.pubsub import get_top_anomalous_atms

        mock_client = MagicMock()
        mock_client.zrevrange.return_value = [
            ("ATM-GB-0001", 15.0),
            ("ATM-GB-0003", 8.0),
        ]
        mock_get_client.return_value = mock_client

        result = get_top_anomalous_atms(limit=2)

        assert result == [
            {"atm_id": "ATM-GB-0001", "count": 15},
            {"atm_id": "ATM-GB-0003", "count": 8},
        ]

    @patch("backend.src.alerts.pubsub.get_redis_client")
    def test_get_top_anomalous_atms_empty_when_redis_down(self, mock_get_client):
        """Test that top ATMs returns empty list when Redis is unavailable."""
        from backend.src.alerts.pubsub import get_top_anomalous_atms

        mock_get_client.return_value = None

        result = get_top_anomalous_atms()

        assert result == []
