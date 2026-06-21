"""Tests for RAG utility functions."""

from backend.src.rag.utils import (
    detect_query_intent,
    extract_atm_id_from_query,
    QueryIntent,
    classify_query_type,
    QueryType,
)


class TestExtractAtmIdFromQuery:
    """Tests for ATM ID extraction from queries."""

    def test_exact_format(self):
        assert extract_atm_id_from_query("ATM-GB-0001") == "ATM-GB-0001"
        assert extract_atm_id_from_query("ATM-GB-0005") == "ATM-GB-0005"
        assert extract_atm_id_from_query("ATM-GB-0010") == "ATM-GB-0010"

    def test_atm_number_shorthand(self):
        assert extract_atm_id_from_query("ATM 1") == "ATM-GB-0001"
        assert extract_atm_id_from_query("ATM 5") == "ATM-GB-0005"
        assert extract_atm_id_from_query("ATM 10") == "ATM-GB-0010"
        assert extract_atm_id_from_query("ATM-1 ") == "ATM-GB-0001"
        assert extract_atm_id_from_query("ATM_5") == "ATM-GB-0005"

    def test_legacy_format(self):
        assert extract_atm_id_from_query("ATM-0001") == "ATM-GB-0001"
        assert extract_atm_id_from_query("ATM-0005") == "ATM-GB-0005"

    def test_no_match(self):
        assert extract_atm_id_from_query("show me logs") is None
        assert extract_atm_id_from_query("ATM 15") is None
        assert extract_atm_id_from_query("ATM-0011") is None

    def test_case_insensitive(self):
        assert extract_atm_id_from_query("atm-gb-0001") == "ATM-GB-0001"
        assert extract_atm_id_from_query("AtM 5") == "ATM-GB-0005"


class TestDetectQueryIntent:
    """Tests for query intent detection."""

    def test_error_keywords(self):
        result = detect_query_intent("what errors occurred")
        assert result.error_only is True

        result = detect_query_intent("show me issues with ATM 1")
        assert result.error_only is True

        result = detect_query_intent("what problems happened")
        assert result.error_only is True

        result = detect_query_intent("any failures recently")
        assert result.error_only is True

    def test_recent_keywords(self):
        result = detect_query_intent("most recent errors")
        assert result.most_recent_first is True

        result = detect_query_intent("latest issues")
        assert result.most_recent_first is True

        result = detect_query_intent("recent logs")
        assert result.most_recent_first is True

    def test_combined_intent(self):
        result = detect_query_intent("most recent issues with ATM 1")
        assert result.error_only is True
        assert result.most_recent_first is True

    def test_no_special_keywords(self):
        result = detect_query_intent("show me all logs")
        assert result.error_only is False
        assert result.most_recent_first is False


class TestQueryIntent:
    """Tests for QueryIntent dataclass."""

    def test_default_values(self):
        intent = QueryIntent()
        assert intent.error_only is False
        assert intent.most_recent_first is False

    def test_custom_values(self):
        intent = QueryIntent(error_only=True, most_recent_first=True)
        assert intent.error_only is True
        assert intent.most_recent_first is True


class TestClassifyQueryType:
    """Tests for query type classification."""

    def test_stats_keywords_how_many(self):
        assert classify_query_type("how many anomalies are there") == QueryType.STATS
        assert classify_query_type("how many errors") == QueryType.STATS
        assert classify_query_type("how many ATMs are down") == QueryType.STATS

    def test_stats_keywords_count_of(self):
        assert classify_query_type("count of A1 errors") == QueryType.STATS
        assert classify_query_type("count of anomalies by type") == QueryType.STATS

    def test_stats_keywords_total(self):
        assert classify_query_type("total anomalies today") == QueryType.STATS
        assert classify_query_type("total errors") == QueryType.STATS
        assert classify_query_type("what is the total count") == QueryType.STATS

    def test_stats_keywords_number_of(self):
        assert classify_query_type("number of critical issues") == QueryType.STATS
        assert classify_query_type("number of ATMs with issues") == QueryType.STATS

    def test_troubleshooting_keywords(self):
        assert classify_query_type("how to fix network timeout") == QueryType.TROUBLESHOOTING
        assert classify_query_type("how to resolve cassette empty") == QueryType.TROUBLESHOOTING
        assert classify_query_type("what to do about OOM error") == QueryType.TROUBLESHOOTING
        assert classify_query_type("how do I fix this") == QueryType.TROUBLESHOOTING
        assert classify_query_type("steps to restart ATM") == QueryType.TROUBLESHOOTING

    def test_diagnostic_keywords(self):
        assert classify_query_type("what's wrong with ATM 3") == QueryType.DIAGNOSTIC
        assert classify_query_type("what is wrong with the machine") == QueryType.DIAGNOSTIC
        assert classify_query_type("why is ATM-GB-0001 slow") == QueryType.DIAGNOSTIC
        assert classify_query_type("why are response times high") == QueryType.DIAGNOSTIC
        assert classify_query_type("what caused the failure") == QueryType.DIAGNOSTIC
        assert classify_query_type("root cause of the issue") == QueryType.DIAGNOSTIC

    def test_general_queries(self):
        assert classify_query_type("tell me about recent issues") == QueryType.GENERAL
        assert classify_query_type("show me the logs") == QueryType.GENERAL
        assert classify_query_type("explain this error") == QueryType.GENERAL
        assert classify_query_type("what happened today") == QueryType.GENERAL

    def test_priority_stats_over_general(self):
        assert classify_query_type("how many") == QueryType.STATS
        assert classify_query_type("count of") == QueryType.STATS

    def test_priority_troubleshooting_over_diagnostic(self):
        assert classify_query_type("how to fix what is wrong") == QueryType.TROUBLESHOOTING