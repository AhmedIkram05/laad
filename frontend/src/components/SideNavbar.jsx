/*
 * SideNavbar Component
 * --------------------
 * A side bar for navigation to main pages.
 */

/* External Libraries */
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { GoHome, GoStar, GoCheckCircle, GoSignOut } from "react-icons/go";
import { FiSettings } from "react-icons/fi";
import { FiActivity } from "react-icons/fi";

/* Internal Imports */
import './SideNavbar.css'

function SideNavbar() {
  const navigate = useNavigate();
  const location = useLocation();

  const active = (path) => location.pathname === path;
  const { user, logout } = useAuth();

  return (
    <div className="navbarContainer">
    
      {/* Main Buttons */}
      <div className="buttonContainer">
        <button className={`button ${active("/dashboard") ? "active" : ""}`} onClick={() => navigate("/dashboard")}>
          <span className="icon"><GoHome/></span><span className="text">Dashboard</span></button>
        <button className={`button ${active("/analytics") ? "active" : ""}`} onClick={() => navigate("/analytics")}>
          <span className="icon"><FiActivity/></span><span className="text">Analytics</span></button>
        <button className={`button ${active("/starred") ? "active" : ""}`} onClick={() => navigate("/starred")}>
          <span className="icon"><GoStar/></span><span className="text">Starred</span></button>
        <button className={`button ${active("/completed") ? "active" : ""}`} onClick={() => navigate("/completed")}>
          <span className="icon"><GoCheckCircle/></span><span className="text">Completed</span></button>
      </div>

      {/* Settings and Account Buttons */}
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