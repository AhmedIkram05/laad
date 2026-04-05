/*
 * Starred Page
 * --------------------
 * Displays all anomalies in the "Starred" state in a list.
 */

/* Internal Imports */
import AnomalyListPage from "../components/AnomalyListPage";

const starredFilter = (a) => !!a.is_starred;

function Starred() {
  return(

    <AnomalyListPage
      title="Starred Anomalies"
      filter={starredFilter}
      isActive={1}
      subtitle="Anomalies saved across ATM and server systems, prioritised by severity."
    />

  );
}

export default Starred;