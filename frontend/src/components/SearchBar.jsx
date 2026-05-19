/*
 * SearchBar Component
 * --------------------
 * A search bar to apply filtering to anomaly lists.
 */

/* External Libraries */
import { GoSearch } from "react-icons/go";

/* Internal Imports */
import './SearchBar.css';

function SearchBar({ search, setSearch }) {

  return (
    <div className="barContainer">

      {/* Search Bar */}
      <div className="searchContainer">
        <GoSearch className="searchIcon" />
        <input
          type="text"
          placeholder="Search by title..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="searchInput"
        />
      </div>

    </div>
  );
}

export default SearchBar;