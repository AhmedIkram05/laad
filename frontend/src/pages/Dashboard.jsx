/*
 * Dashboard Page
 * --------------------
 * Displays all anomalies in a list with analytics, timeline, and log stream.
 */

/* Internal Imports */
import AnomalyListPage from "../components/AnomalyListPage";

function Dashboard() {
  return (
    <AnomalyListPage title="Anomalies Detected" />
  );
}

export default Dashboard;