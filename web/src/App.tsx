import { Route, Routes } from "react-router-dom";
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
import { EmptyState } from "./components/ui";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/organizations" element={<OrganizationsPage />} />
        <Route path="/organizations/:key" element={<OrganizationPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/events/:eventId" element={<EventsPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/sources" element={<SourcesPage />} />
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
