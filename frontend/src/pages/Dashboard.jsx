/* Import Components */
import StarIcon from "../components/StarIcon";

/* Import Icons */
import { GoAlert } from "react-icons/go";

/* Import Styles */
import './Dashboard.css'


function Dashboard() {
  return (
    <>

      {/* Search and Filter Bar */}
      <div className="searchContainer">
        <p>Search Bar</p>
      </div>

      {/* Main Page Content */}
      <div className="mainContainer">
 
        {/* Title and Count */}
        <div className="titleContainer">
          <h1>Anomalies Detected</h1>
          <h2>[count]</h2>
        </div>

        {/* Anomaly Cards */}
        <div className="anomalyContainer">

          <div className="anomalyCard">

            <div className="cardDetails">

              <div className="alert">
                <div className="alertIcon"><GoAlert /></div>
                <h3>Cassette Empty</h3>
              </div>

              <div className="minorDetails">
                <p>ATM-GB-0003</p>
                <div className="detailsContainer">
                  <p>4 anomalies</p>
                  <p>Updated: 2 mins ago</p>
                </div>
              </div>
            </div>

            <div className="cardButtons">
              <button className="viewButton">View</button>
              <StarIcon />
            </div>
          </div>

        </div>

      </div>

    </>
  );
}


export default Dashboard;