import { Search, X } from "lucide-react";
import { Input } from "./ui/input";
import { useGlobalSearch } from "./SearchContext";

export default function SearchBar({ onQueryChange }) {
  const { query, setQuery } = useGlobalSearch();

  const handleChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    if (onQueryChange) onQueryChange(val);
  };

  const handleClear = () => {
    setQuery("");
    if (onQueryChange) onQueryChange("");
  };

  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <Input
        type="text"
        placeholder="Search anomalies, ATMs, servers, types, severities..."
        value={query}
        onChange={handleChange}
        className="pl-9 pr-9"
      />
      {query && (
        <button
          onClick={handleClear}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 rounded-md hover:bg-secondary transition-colors"
          aria-label="Clear search"
        >
          <X className="w-4 h-4 text-muted-foreground" />
        </button>
      )}
    </div>
  );
}
