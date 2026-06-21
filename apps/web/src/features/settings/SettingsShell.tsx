import { Navigate, NavLink, Route, Routes } from "react-router-dom";

import { PageContainer } from "@/components";
import { useSession } from "@/session/SessionContext";

import { DataSection } from "./sections/DataSection";
import { MembersSection } from "./sections/MembersSection";
import { ModelPolicySection } from "./sections/ModelPolicySection";
import { OperationsSection } from "./sections/OperationsSection";
import { PermissionsSection } from "./sections/PermissionsSection";
import { ProvidersSection } from "./sections/ProvidersSection";
import { WorkspaceSection } from "./sections/WorkspaceSection";
import styles from "./settings.module.css";

interface SectionLink {
  path: string;
  label: string;
  operatorOnly?: boolean;
}

const SECTIONS: SectionLink[] = [
  { path: "workspace", label: "Workspace" },
  { path: "members", label: "Members" },
  { path: "permissions", label: "Permissions" },
  { path: "model-policy", label: "Model policy" },
  { path: "data", label: "Data & erasure" },
  { path: "providers", label: "Providers", operatorOnly: true },
  { path: "operations", label: "Operations", operatorOnly: true },
];

/**
 * The Settings shell (G1): a sub-nav over the subsections + the routed content. Operations is
 * operator-only — hidden from the nav and guarded on the route. G2–G5 fill Members / Permissions /
 * Model policy / Operations.
 */
export function SettingsShell() {
  const { isOperator } = useSession();
  const sections = SECTIONS.filter((s) => !s.operatorOnly || isOperator);

  return (
    <PageContainer wide>
      <h1 className={styles.title}>Settings</h1>
      <div className={styles.layout}>
        <nav className={styles.subnav} aria-label="Settings sections">
          {sections.map((section) => (
            <NavLink
              key={section.path}
              to={`/settings/${section.path}`}
              className={({ isActive }) =>
                isActive ? `${styles.subnavLink} ${styles.subnavLinkActive}` : styles.subnavLink
              }
            >
              {section.label}
            </NavLink>
          ))}
        </nav>
        <div className={styles.content}>
          <Routes>
            <Route index element={<Navigate to="workspace" replace />} />
            <Route path="workspace" element={<WorkspaceSection />} />
            <Route path="members" element={<MembersSection />} />
            <Route path="permissions" element={<PermissionsSection />} />
            <Route path="model-policy" element={<ModelPolicySection />} />
            <Route path="data" element={<DataSection />} />
            <Route
              path="providers"
              element={isOperator ? <ProvidersSection /> : <Navigate to="/settings/workspace" replace />}
            />
            <Route
              path="operations"
              element={isOperator ? <OperationsSection /> : <Navigate to="/settings/workspace" replace />}
            />
            <Route path="*" element={<Navigate to="/settings/workspace" replace />} />
          </Routes>
        </div>
      </div>
    </PageContainer>
  );
}
