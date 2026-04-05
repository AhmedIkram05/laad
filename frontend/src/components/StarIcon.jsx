/*
 * StarIcon Component
 * --------------------
 * A star icon for toggling appearance while switching between "Starred" states.
 */

/* External Libraries */
import { GoStar, GoStarFill } from "react-icons/go";

/* Internal Imports */
import "./StarIcon.css";

function StarIcon({ id, isStarred, toggleStar }) {
    return (
        <button className="starButton" onClick={() => toggleStar(id)}>
            {isStarred ? <GoStarFill /> : <GoStar />}
        </button>
    );
}

export default StarIcon;