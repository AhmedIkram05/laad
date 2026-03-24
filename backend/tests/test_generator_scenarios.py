import json
import os
import csv
import tempfile
import unittest
from datetime import datetime
from backend.ingestion.custom_data_generator import generate_dataset, SCENARIO_CORR

class TestGeneratorScenarios(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def test_scenarios_generated_correctly(self):
        # Generate smaller dataset for speed
        generate_dataset(output=self.test_dir, hours=24)
        
        # Load datasets
        with open(os.path.join(self.test_dir, "atm_application_log.json")) as f:
            app_logs = json.load(f)
        with open(os.path.join(self.test_dir, "kafka_atm_metrics_stream.json")) as f:
            kafka_logs = json.load(f)
        with open(os.path.join(self.test_dir, "terminal_handler_app_log.json")) as f:
            terminal_logs = json.load(f)
        with open(os.path.join(self.test_dir, "atm_hardware_sensor_log.json")) as f:
            hw_logs = json.load(f)
            
        # A1 Verification
        a1_app = [r for r in app_logs if r.get("correlation_id") == SCENARIO_CORR["A1"]]
        self.assertTrue(any(r["event_type"] == "NETWORK_DISCONNECT" for r in a1_app))
        self.assertTrue(any(r["event_type"] == "TIMEOUT" for r in a1_app))
        
        a1_kafka = [r for r in kafka_logs if r.get("correlation_id") == SCENARIO_CORR["A1"]]
        self.assertTrue(any(r["atm_status"] == "Offline" for r in a1_kafka))
        
        a1_term = [r for r in terminal_logs if r.get("correlation_id") == SCENARIO_CORR["A1"]]
        self.assertTrue(any(r["event_type"] == "NETWORK_TIMEOUT" for r in a1_term))

        # A2 Verification
        a2_hw = [r for r in hw_logs if r.get("correlation_id") == SCENARIO_CORR["A2"]]
        self.assertTrue(any(r["event_type"] == "CASSETTE_EMPTY" and r["severity"] == "CRITICAL" for r in a2_hw))
        
        a2_kafka = [r for r in kafka_logs if r.get("correlation_id") == SCENARIO_CORR["A2"]]
        self.assertTrue(any(r["atm_status"] == "Out of Service" and r["transaction_failure_reason"] == "CASH_DISPENSE_ERROR" for r in a2_kafka))

        # A3 Verification
        a3_prom = [r for r in csv.DictReader(open(os.path.join(self.test_dir, "prometheus_metrics.csv"))) if r.get("_anomaly") == "A3_LEAK"]
        self.assertTrue(len(a3_prom) >= 10)
        # Check monotonic rise (simple check: last > first)
        self.assertGreater(float(a3_prom[-1]["metric_value"]), float(a3_prom[0]["metric_value"]))
        
        a3_term = [r for r in terminal_logs if r.get("_anomaly") == "A3_FATAL"]
        self.assertTrue(any(r["exception_class"] == "OutOfMemoryError" for r in a3_term))

        # A4 Verification
        a4_term_start = [r for r in terminal_logs if r.get("_anomaly") == "A4_STARTUP"]
        self.assertEqual(len(a4_term_start), 3)
        a4_gcp = [r for r in csv.DictReader(open(os.path.join(self.test_dir, "gcp_cloud_metrics.csv"))) if r.get("_anomaly") == "A4_RESTART"]
        self.assertTrue(any(r["restart_count"] == "2" for r in a4_gcp))

        # A5 Verification
        a5_kafka = [r for r in kafka_logs if r.get("correlation_id") == SCENARIO_CORR["A5"]]
        self.assertTrue(any(float(r["response_time_ms"]) >= 3000 for r in a5_kafka))

        # A6 Verification
        a6_win = [r for r in csv.DictReader(open(os.path.join(self.test_dir, "windows_os_metrics.csv"))) if r.get("_anomaly") == "A6_RAMP"]
        self.assertGreater(float(a6_win[-1]["memory_usage_percent"]), 90.0)
        a6_app = [r for r in app_logs if r.get("_anomaly") == "A6_TIMEOUT"]
        self.assertTrue(any("memory pressure" in r.get("error_detail", "") for r in a6_app))

        # A7 Verification
        a7_nulls = [r for r in kafka_logs if r.get("_anomaly") == "A7_NULLS"]
        self.assertTrue(len(a7_nulls) > 0)
        self.assertIsNone(a7_nulls[0]["atm_status"])

if __name__ == "__main__":
    unittest.main()
