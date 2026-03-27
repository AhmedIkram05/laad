/* Import Icons */
import { GoSearch, GoFilter } from "react-icons/go";

/* Import Styles */
import './SearchBar.css';


function SearchBar({ search, setSearch, filterBy, setFilterBy }) {

  // Filtering Options
  const filterOptions = [
    { label: "Title", value: "title" },
    { label: "ID", value: "ID" }
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