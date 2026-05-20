import AnomalyListPage from "../components/AnomalyListPage";

function Completed() {
  return (
    <AnomalyListPage 
      title="Completed Anomalies" 
      subtitle="Resolved and completed anomalies that have been addressed."
      isActive={0}
    />
  );
}

export default Completed;