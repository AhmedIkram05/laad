/* Import Components */
import AnomalyListPage from "../components/AnomalyListPage";

const completedFilter = (a) => a.is_active === 0;

function Completed() {
    return <AnomalyListPage title="Completed Anomalies" filter={completedFilter} isActive={0} />;
}

export default Completed;
