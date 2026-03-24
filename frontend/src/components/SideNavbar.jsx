/* Import Libraries */
import { useNavigate } from "react-router-dom";

/* Import Styles */
import './SideNavbar.css'


function SideNavbar() {
  const navigate = useNavigate();

  return (
    <div className="navbarContainer">
      <button className="button" onClick={() => navigate("/dashboard")}>
        Dashboard
      </button>
    </div>
  );
}


export default SideNavbar;