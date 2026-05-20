import { Outlet } from "react-router-dom";
import { Sidebar } from "../components/Sidebar";
import { cn } from "../lib/utils";

export default function MainLayout() {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main
        className={cn(
          "flex-1 transition-all duration-200",
          "ml-[64px] lg:ml-[240px]"
        )}
      >
        <div className="p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}