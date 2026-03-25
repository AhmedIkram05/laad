/* Import Components */
import StarIcon from "../components/StarIcon";

/* Import Icons */
import { GoAlert } from "react-icons/go";


function AnomalyCard({ title, atmID, count, updatedTime }) {
  return (

    <div className="card">

      <div className="body">

        <div className="title">
          <div className="alertIcon"><GoAlert /></div>
            <h3>{title}</h3>
        </div>

        <div className="details">
          <p>{atmID}</p>
          <div className="updates">
            <p>{count}</p>
            <p>{updatedTime}</p>
          </div>
        </div>

      </div>

      <div className="buttons">
        <button className="view">View</button>
        <StarIcon />
      </div>
          
    </div>

  );
}


export default Anomaly Card;