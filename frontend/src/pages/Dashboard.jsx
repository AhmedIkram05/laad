import AnomalyListPage from "../components/AnomalyListPage";

function Dashboard() {
  return (
    <AnomalyListPage
      title="Anomalies Detected"
      subtitle="Detected anomalies across ATM and server systems, prioritised by severity."
      isActive={1}
    />
  );
}

export default Dashboard;
