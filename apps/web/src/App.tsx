import { Route, Routes } from "react-router-dom";

import { AppShell } from "@/app/AppShell";
import { IndexRedirect, NotFound, RequireRole } from "@/app/guards";
import { ActivityPage } from "@/pages/ActivityPage";
import { AskPage } from "@/pages/AskPage";
import { DesignSystemPage } from "@/pages/DesignSystemPage";
import { LoginPage } from "@/pages/LoginPage";
import { RedeemPage } from "@/pages/RedeemPage";
import { ReviewPage } from "@/pages/ReviewPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SourcesPage } from "@/pages/SourcesPage";
import { useSession } from "@/session/SessionContext";

function LoadingScreen() {
  return (
    <div className="loading-screen" role="status" aria-live="polite">
      Loading…
    </div>
  );
}

/**
 * Router root (B3). While the session restores, a loading screen. Anonymous users get the
 * sign-in screen (with /redeem and /design still reachable); authenticated users get the role-gated
 * shell. B4 fills the header's workspace switcher + scope selector.
 */
export function App() {
  const { status } = useSession();
  if (status === "loading") return <LoadingScreen />;

  return (
    <Routes>
      <Route path="/design" element={<DesignSystemPage />} />
      <Route path="/redeem/:token" element={<RedeemPage />} />
      {status === "authenticated" ? (
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
      ) : (
        <Route path="*" element={<LoginPage />} />
      )}
    </Routes>
  );
}
