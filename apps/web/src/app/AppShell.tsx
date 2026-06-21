import { NavLink, Outlet } from "react-router-dom";

import type { WorkspaceKind } from "@/api/types";
import { Badge, Button, ScopeBadge } from "@/components";
import type { WorkspaceScope } from "@/domain/types";
import { useSession } from "@/session/SessionContext";

import { navForRole } from "./nav";
import styles from "./AppShell.module.css";

function initials(email: string): string {
  const name = email.split("@")[0] ?? email;
  return name.slice(0, 2).toUpperCase();
}

const scopeForKind = (kind: WorkspaceKind): WorkspaceScope => (kind === "personal" ? "personal" : "shared");

/** Header: brand, the active workspace + scope (B4 makes the switcher interactive), and the user menu. */
function Header() {
  const { user, role, isOperator, activeWorkspace, signOut } = useSession();
  if (!user) return null;

  return (
    <header className={styles.header}>
      <span className={styles.brand}>
        Metis
        <span className={styles.brandTag}>context exoskeleton</span>
      </span>

      <div className={styles.headerSlot}>
        {/* Shows the real active workspace; B4 turns this into the switcher dropdown. */}
        <button type="button" className={styles.wsButton} disabled aria-label="Active workspace">
          {activeWorkspace?.name ?? "No workspace"}
        </button>
        {activeWorkspace && <ScopeBadge scope={scopeForKind(activeWorkspace.kind)} />}
      </div>

      <span className={styles.spacer} />

      <details className={styles.menu}>
        <summary aria-label="Account menu">
          <span className={styles.avatar} aria-hidden="true">
            {initials(user.email)}
          </span>
          <span className={styles.menuEmail}>{user.email}</span>
        </summary>
        <div className={styles.menuPanel}>
          <div className={styles.menuLabel}>Signed in</div>
          <div style={{ fontSize: "var(--text-sm)" }}>{user.email}</div>
          <div className={styles.menuRow}>
            <Badge variant="neutral">{role}</Badge>
            {isOperator && <Badge variant="accent">operator</Badge>}
          </div>
          <div className={styles.menuDivider} />
          <Button variant="secondary" block onClick={signOut}>
            Sign out
          </Button>
        </div>
      </details>
    </header>
  );
}

/** Role-filtered left nav (≤5 persistent sections). */
function Sidebar() {
  const { role } = useSession();
  const items = navForRole(role);
  return (
    <nav className={styles.sidebar} aria-label="Primary">
      {items.map((item) => (
        <NavLink
          key={item.id}
          to={item.path}
          className={({ isActive }) =>
            isActive ? `${styles.navLink} ${styles.navLinkActive}` : styles.navLink
          }
        >
          <span className={styles.navIcon}>{item.icon}</span>
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

/** The application shell: header + role-gated nav + routed content. */
export function AppShell() {
  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Header />
      <div className={styles.body}>
        <Sidebar />
        <main id="main" className={styles.content}>
          <div className={styles.contentInner}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
