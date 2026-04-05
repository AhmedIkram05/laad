/*
 * SearchBar Component
 * --------------------
 * A search bar to apply filtering to anomaly lists.
 */

/* External Libraries */
import { GoSearch, GoFilter } from "react-icons/go";

/* Internal Imports */
import './SearchBar.css';

function SearchBar({ search, setSearch, filterBy, setFilterBy }) {

  // Filtering Options
  const filterOptions = [
    { label: "Title", value: "title" },
    { label: "ATM ID", value: "atm_id" }
  ];

  return (
    <div className="barContainer">

      {/* Search Bar */}
      <div className="searchContainer">
        <GoSearch className="searchIcon" />
        <input
          type="text"
          placeholder={`Search by ${filterBy}...`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="searchInput"
      />
      </div>

      {/* Filter Dropdown */}
      <div className="filterContainer">
        <GoFilter className="filterIcon" />
        <select className="filterBox" value={filterBy} onChange={(e) => setFilterBy(e.target.value)}>
          {filterOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      </div>
  );
}

export default SearchBar;