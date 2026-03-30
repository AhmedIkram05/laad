/* Import Libraries */
import { GoStar, GoStarFill } from "react-icons/go";

/* Import Styles */
import "./StarIcon.css";

function StarIcon({ id, isStarred, toggleStar }) {
    return (
        <button className="starButton" onClick={() => toggleStar(id)}>
            {isStarred ? <GoStarFill /> : <GoStar />}
        </button>
    );
}

export default StarIcon;
