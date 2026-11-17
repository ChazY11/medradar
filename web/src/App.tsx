import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ComparePage } from "./pages/ComparePage";
import { EventsPage } from "./pages/EventsPage";
import { OrganizationPage } from "./pages/OrganizationPage";
import { OrganizationsPage } from "./pages/OrganizationsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReviewPage } from "./pages/ReviewPage";
import { DevicesPage } from "./pages/DevicesPage";
import { DevicePage } from "./pages/DevicePage";
import { SourcesPage } from "./pages/SourcesPage";
import { DataStatusPage } from "./pages/DataStatusPage";
import { BriefPage } from "./pages/BriefPage";
import { LiveIntelligencePage } from "./pages/LiveIntelligencePage";
import { TechnologyMapPage } from "./pages/TechnologyMapPage";
import { EmptyState } from "./components/ui";
import { IS_PUBLIC_ALPHA } from "./lib/alpha";

export default function App() {
  if (IS_PUBLIC_ALPHA) {
    // The public deployment only serves the Radar pages and the read-only Radar API. Routing
    // the workbench pages here produced buttons that could only ever 404; on the public site
    // they do not exist, and any old URL lands on the live feed.
    return (
      <AppShell>
        <Routes>
          <Route path="/" element={<LiveIntelligencePage />} />
          <Route path="/radar" element={<LiveIntelligencePage />} />
          <Route path="/radar/technology-map" element={<TechnologyMapPage />} />
          <Route path="*" element={<Navigate to="/radar" replace />} />
        </Routes>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/brief" element={<BriefPage />} />
        <Route path="/radar" element={<LiveIntelligencePage />} />
        <Route path="/radar/technology-map" element={<TechnologyMapPage />} />
        <Route path="/organizations" element={<OrganizationsPage />} />
        <Route path="/organizations/:key" element={<OrganizationPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/events/:eventId" element={<EventsPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/data-status" element={<DataStatusPage />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="/devices/:deviceId" element={<DevicePage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route
          path="*"
          element={
            <EmptyState
              title="Page not found"
              description="This route does not exist in the workbench. Use the navigation above."
            />
          }
        />
      </Routes>
    </AppShell>
  );
}
