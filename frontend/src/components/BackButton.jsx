/* Import Libraries */
import { useNavigate } from "react-router-dom";
import { GoChevronLeft } from "react-icons/go";

/* Import Styles */
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