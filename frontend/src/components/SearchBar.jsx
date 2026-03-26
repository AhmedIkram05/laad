// Import Icons
import { GoSearch } from "react-icons/go";

// Import Styles
import './SearchBar.css';


function SearchBar({ search, setSearch }) {
  return (

    <div className="searchContainer">

      <GoSearch className="searchIcon" />

      <input
        type="text"
        placeholder="Search anomalies..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="searchInput"
      />
      
    </div>

  );
}


export default SearchBar;