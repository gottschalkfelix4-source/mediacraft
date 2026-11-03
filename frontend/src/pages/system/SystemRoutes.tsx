import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { PageHeader } from "../../components/ui";
import { SYSTEM_NAV } from "../../components/Layout";
import { StatusPage } from "./StatusPage";
import { TasksPage } from "./TasksPage";
import { LogsPage } from "./LogsPage";
import { LibraryImportPage } from "./LibraryImport";
import { ManualImportPage } from "./ManualImport";
import { BackupPage } from "./BackupPage";
import { RecycleBinPage } from "./RecycleBin";

export function SystemRoutes() {
  return (
    <div className="page">
      <PageHeader title="System" />
      <nav className="subnav" aria-label="Systembereiche">
        {SYSTEM_NAV.map((n) => (
          <NavLink key={n.to} to={n.to} className={({ isActive }) => `subnav-link ${isActive ? "active" : ""}`}>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to="status" replace />} />
        <Route path="status" element={<StatusPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="backup" element={<BackupPage />} />
        <Route path="recyclebin" element={<RecycleBinPage />} />
        <Route path="libraryimport" element={<LibraryImportPage />} />
        <Route path="manualimport" element={<ManualImportPage />} />
        <Route path="*" element={<Navigate to="status" replace />} />
      </Routes>
    </div>
  );
}
