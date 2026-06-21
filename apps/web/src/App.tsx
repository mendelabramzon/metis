import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/app/AppShell";
import { IndexRedirect, NotFound, RequireRole } from "@/app/guards";
import { ActivityPage } from "@/pages/ActivityPage";
import { AskPage } from "@/pages/AskPage";
import { DesignSystemPage } from "@/pages/DesignSystemPage";
import { ReviewPage } from "@/pages/ReviewPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SourcesPage } from "@/pages/SourcesPage";

/**
 * Router root (B2). The five role-gated sections render inside the AppShell; /design is a
 * standalone reference route for the design-system gallery. Login/session (B3) will wrap the shell
 * routes in an auth boundary; the workspace switcher + scope selector (B4) fill the header slots.
 */
export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<IndexRedirect />} />
        <Route
          path="ask"
          element={
            <RequireRole navId="ask">
              <AskPage />
            </RequireRole>
          }
        />
        <Route
          path="sources"
          element={
            <RequireRole navId="sources">
              <SourcesPage />
            </RequireRole>
          }
        />
        <Route
          path="review"
          element={
            <RequireRole navId="review">
              <ReviewPage />
            </RequireRole>
          }
        />
        <Route
          path="activity"
          element={
            <RequireRole navId="activity">
              <ActivityPage />
            </RequireRole>
          }
        />
        <Route
          path="settings"
          element={
            <RequireRole navId="settings">
              <SettingsPage />
            </RequireRole>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="/design" element={<DesignSystemPage />} />
    </Routes>
  );
}
