/* Import Libraries */
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

/* Import Icons */
import { GoHome, GoStar, GoCheckCircle, GoSignOut } from "react-icons/go";
import { FiSettings } from "react-icons/fi";

/* Import Styles */
import './SideNavbar.css'


function SideNavbar() {
  const navigate = useNavigate();
  const location = useLocation();

  const active = (path) => location.pathname === path;

  const { user, logout } = useAuth();

  return (
    <div className="navbarContainer">
    
      <div className="buttonContainer">
        <button className={`button ${active("/dashboard") ? "active" : ""}`} onClick={() => navigate("/dashboard")}>
          <span className="icon"><GoHome/></span><span className="text">Dashboard</span></button>
        <button className={`button ${active("/starred") ? "active" : ""}`} onClick={() => navigate("/starred")}>
          <span className="icon"><GoStar/></span><span className="text">Starred</span></button>
        <button className={`button ${active("/completed") ? "active" : ""}`} onClick={() => navigate("/completed")}>
          <span className="icon"><GoCheckCircle/></span><span className="text">Completed</span></button>
      </div>

      <div className="settingsContainer">
        <div className="buttonContainer">
          {user && user.role === "admin" && (
            <button className={`button ${active("/admin/settings") ? "active" : ""}`} onClick={() => navigate("/admin/settings")}>
              <span className="icon"><FiSettings/></span><span className="text">Admin Settings</span>
            </button>)}
          <button className="button" onClick={() => { logout(); navigate("/login", { replace: true }); }}>
            <span className="icon"><GoSignOut/></span><span className="text">Log Out</span>
          </button>
        </div>
      </div>

    </div>
  );
}


export default SideNavbar;