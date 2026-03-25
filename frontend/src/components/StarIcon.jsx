/* Import Libraries */
import { useState } from "react";

/* Import Icons */
import { GoStar, GoStarFill } from "react-icons/go";

/* Import Styles */
import './StarIcon.css'


function StarIcon() {
  const [isStarred, setIsStarred] = useState(false);

  return (
    <button className="starButton" onClick={() => setIsStarred(prev => !prev)}>{isStarred ? <GoStarFill /> : <GoStar />}</button>
  );
}


export default StarIcon;