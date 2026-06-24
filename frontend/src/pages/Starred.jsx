import AnomalyListPage from "../components/AnomalyListPage";

function Starred() {
  return (
    <AnomalyListPage
      title="Starred Anomalies"
      subtitle="Quick access to your starred anomalies for priority monitoring."
      isActive={1}
      isStarred={1}
    />
  );
}

export default Starred;
