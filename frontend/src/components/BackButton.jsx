import { useNavigate } from "react-router-dom";
import { ChevronLeft } from "lucide-react";

function BackButton() {
  const navigate = useNavigate();

  return(
    <button
      onClick={() => navigate(-1)}
      className="flex items-center gap-1 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md transition-colors"
    >
      <ChevronLeft className="w-4 h-4" />
      <span>Back</span>
    </button>
  )
}

export default BackButton;