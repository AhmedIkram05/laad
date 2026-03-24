/* Import Libraries */
import { useNavigate } from "react-router-dom";

/* Import Icons */
import { GoHome, GoStar, GoCheckCircle, GoSignOut, GoTools } from "react-icons/go";

/* Import Styles */
import './SideNavbar.css'


function SideNavbar() {
  const navigate = useNavigate();

  return (
    <div className="navbarContainer">
    
      <div className="buttonContainer">
        <button className="button" onClick={() => navigate("/dashboard")}>
          <span className="icon"><GoHome/></span><span className="text">Dashboard</span></button>
        <button className="button" onClick={() => navigate("/starred")}>
          <span className="icon"><GoStar/></span><span className="text">Starred</span></button>
        <button className="button" onClick={() => navigate("/completed")}>
          <span className="icon"><GoCheckCircle/></span><span className="text">Completed</span></button>
      </div>

      <div className="settingsContainer">
        <div className="buttonContainer">
            <button className="button" onClick={() => navigate("/settings")}>
          <span className="icon"><GoTools/></span><span className="text">Settings</span></button>
            <button className="button" onClick={() => navigate("/login")}>
          <span className="icon"><GoSignOut/></span><span className="text">Log Out</span></button>
        </div>
      </div>

    </div>
  );
}


export default SideNavbar;