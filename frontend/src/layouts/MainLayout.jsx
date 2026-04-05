/*
 * Main Layout
 * --------------------
 * A layout applied to all main pages.
 */

/* External Libraries */
import { Outlet } from "react-router-dom";

/* Internal Components */
import SideNavbar from "../components/SideNavbar";
import './MainLayout.css'

function MainLayout() {
  return (

    <div className="container">
      {/* Side Navbar */}
      <SideNavbar/>

      {/* Page content */}
      <div className="page">
        <Outlet/>
      </div>
    </div>

  );
}

export default MainLayout;