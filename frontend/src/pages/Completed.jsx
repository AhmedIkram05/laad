/*
 * Completed Page
 * --------------------
 * Displays all active anomalies (in the "Completed" state) in a list.
 */

/* Internal Imports */
import AnomalyListPage from "../components/AnomalyListPage";

const completedFilter = (a) => a.is_active === 0;

function Completed() {
    return(

    <AnomalyListPage
      title="Completed Anomalies"
      filter={completedFilter}
      isActive={0}
      subtitle="Anomalies marked as resolved."
    />

  );
}

export default Completed;