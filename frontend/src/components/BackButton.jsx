/*
 * BackButton Component
 * --------------------
 * A back button to return to previous page in navigation.
 */

/* External Libraries */
import { useNavigate } from "react-router-dom";
import { GoChevronLeft } from "react-icons/go";

/* Internal Imports */
import "./BackButton.css";

function BackButton() {
  const navigate = useNavigate();

  return(
    <button className="back-button" onClick={() => navigate(-1)}>
      <GoChevronLeft className="back-button-icon" />
    </button>
  )

}

export default BackButton;