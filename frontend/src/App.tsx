import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, onUnauthorized } from "./api";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useLiveEvents } from "./events";
import { useStored } from "./hooks";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { MoviesPage } from "./pages/library/MoviesPage";
import { AddMovie } from "./pages/library/AddMovie";
import { MovieDetail } from "./pages/library/MovieDetail";
import { CollectionsPage } from "./pages/library/Collections";
import { SeriesPage } from "./pages/library/SeriesPage";
import { AddSeries } from "./pages/library/AddSeries";
import { SeriesDetail } from "./pages/library/SeriesDetail";
import { CalendarPage } from "./pages/Calendar";
import { ActivityPage } from "./pages/Activity";
import { WantedPage } from "./pages/Wanted";
import { IndexersPage } from "./pages/indexers/IndexersPage";
import { IndexerUsagePage } from "./pages/indexers/IndexerUsage";
import { SettingsRoutes } from "./pages/settings/SettingsRoutes";
import { SystemRoutes } from "./pages/system/SystemRoutes";

export function App() {
  const [theme, setTheme] = useStored<"dark" | "light">("mc-theme", "dark");
  const qc = useQueryClient();
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.authStatus, staleTime: Infinity, retry: 1 });
  const [needLogin, setNeedLogin] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    onUnauthorized(() => setNeedLogin(true));
  }, []);

  const authed = !!auth.data && (auth.data.authenticated || auth.data.method === "none") && !needLogin;
  const connected = useLiveEvents(authed);

  if (auth.isLoading) return <Loading label="Verbinde mit MediaCraft…" />;
  if (auth.error)
    return (
      <div className="login-page">
        <div className="login-card">
          <h1>MediaCraft</h1>
          <p className="tone-text-danger">Server nicht erreichbar.</p>
          <button className="btn btn-primary" onClick={() => auth.refetch()}>
            Erneut versuchen
          </button>
        </div>
      </div>
    );

  if (!authed)
    return (
      <Login
        onDone={async () => {
          setNeedLogin(false);
          await qc.invalidateQueries();
        }}
      />
    );

  const logout = async () => {
    await api.logout().catch(() => undefined);
    qc.clear();
    setNeedLogin(true);
    auth.refetch();
  };

  return (
    <Layout
      theme={theme}
      onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
      onLogout={logout}
      connected={connected}
      authMethod={auth.data?.method ?? "none"}
      version={auth.data?.version}
    >
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/movies" element={<MoviesPage />} />
        <Route path="/movies/add" element={<AddMovie />} />
        <Route path="/movies/collections" element={<CollectionsPage />} />
        <Route path="/movies/:id" element={<MovieDetail />} />
        <Route path="/series" element={<SeriesPage />} />
        <Route path="/series/add" element={<AddSeries />} />
        <Route path="/series/:id" element={<SeriesDetail />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="/activity/:tab" element={<ActivityPage />} />
        <Route path="/wanted" element={<WantedPage />} />
        <Route path="/wanted/:tab" element={<WantedPage />} />
        <Route path="/indexers" element={<IndexersPage />} />
        <Route path="/indexers/:id" element={<IndexerUsagePage />} />
        <Route path="/settings/*" element={<SettingsRoutes />} />
        <Route path="/system/*" element={<SystemRoutes />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
