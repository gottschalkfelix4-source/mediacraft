import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { PageHeader } from "../../components/ui";
import { SETTINGS_NAV } from "../../components/Layout";
import { MediaSettings } from "./MediaSettings";
import { ProfilesSettings } from "./ProfilesSettings";
import { CustomFormatsSettings } from "./CustomFormatsSettings";
import { IndexerGeneralSettings } from "./IndexerGeneralSettings";
import { DownloadClientsSettings } from "./DownloadClientsSettings";
import { MetadataSettingsPage } from "./MetadataSettings";
import { NotificationsSettings } from "./NotificationsSettings";
import { AutomationSettings } from "./AutomationSettings";
import { GeneralSettings } from "./GeneralSettings";
import { QualityDefinitionsSettings } from "./QualityDefinitions";

export function SettingsRoutes() {
  return (
    <div className="page">
      <PageHeader title="Einstellungen" />
      <nav className="subnav" aria-label="Einstellungsbereiche">
        {SETTINGS_NAV.map((n) => (
          <NavLink key={n.to} to={n.to} className={({ isActive }) => `subnav-link ${isActive ? "active" : ""}`}>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to="media" replace />} />
        <Route path="media" element={<MediaSettings />} />
        <Route path="profiles" element={<ProfilesSettings />} />
        <Route path="qualities" element={<QualityDefinitionsSettings />} />
        <Route path="customformats" element={<CustomFormatsSettings />} />
        <Route path="indexers" element={<IndexerGeneralSettings />} />
        <Route path="downloadclients" element={<DownloadClientsSettings />} />
        <Route path="metadata" element={<MetadataSettingsPage />} />
        <Route path="notifications" element={<NotificationsSettings />} />
        <Route path="automation" element={<AutomationSettings />} />
        <Route path="general" element={<GeneralSettings />} />
        <Route path="*" element={<Navigate to="media" replace />} />
      </Routes>
    </div>
  );
}
