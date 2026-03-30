/* Import Components */
import AnomalyListPage from "../components/AnomalyListPage";

const starredFilter = (a) => a.is_starred === 1;

function Starred() {
  return <AnomalyListPage title="Starred Anomalies" filter={starredFilter} isActive={1} />;
}

export default Starred;
