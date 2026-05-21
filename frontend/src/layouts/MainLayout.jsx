import { useState, useEffect } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "../components/Sidebar";
import { SearchProvider } from "../components/GlobalSearch";
import { RAGProvider } from "../providers/RAGProvider";

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(() => {
    const stored = localStorage.getItem("sidebar-collapsed");
    return stored ? JSON.parse(stored) : false;
  });

  useEffect(() => {
    localStorage.setItem("sidebar-collapsed", JSON.stringify(collapsed));
  }, [collapsed]);

  return (
    <SearchProvider>
      <RAGProvider>
        <div className="flex min-h-screen bg-background">
          <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
          <main
            className={`flex-1 transition-all duration-200 ${collapsed ? "ml-16" : "ml-60"}`}
          >
            <div className="p-6 lg:p-8">
              <Outlet />
            </div>
          </main>
        </div>
      </RAGProvider>
    </SearchProvider>
  );
}