import { NavLink, Outlet } from "react-router-dom";

import { ScopeBadge } from "@/components";
import { useSession } from "@/session/SessionContext";
import { ROLES } from "@/session/types";
import type { Role } from "@/session/types";

import { navForRole } from "./nav";
import styles from "./AppShell.module.css";

function initials(email: string): string {
  const name = email.split("@")[0] ?? email;
  return name.slice(0, 2).toUpperCase();
}

/** Header: brand, the workspace-switcher slot + scope badge (B4 wires these), and the user menu. */
function Header() {
  const { principal, setRole } = useSession();
  if (!principal) return null;

  return (
    <header className={styles.header}>
      <span className={styles.brand}>
        Metis
        <span className={styles.brandTag}>context exoskeleton</span>
      </span>

      <div className={styles.headerSlot}>
        {/* Placeholder switcher + scope — B4 replaces with the real workspace/scope controls. */}
        <button type="button" className={styles.wsButton} disabled aria-label="Active workspace">
          Personal workspace
        </button>
        <ScopeBadge scope="personal" />
      </div>

      <span className={styles.spacer} />

      <details className={styles.menu}>
        <summary aria-label="Account menu">
          <span className={styles.avatar} aria-hidden="true">
            {initials(principal.email)}
          </span>
          <span className={styles.menuEmail}>{principal.email}</span>
        </summary>
        <div className={styles.menuPanel}>
          <div className={styles.menuLabel}>Active role (demo)</div>
          <div className={styles.roleList} role="radiogroup" aria-label="Active role">
            {ROLES.map((role: Role) => (
              <label key={role} className={styles.roleOption}>
                <input
                  type="radio"
                  name="role"
                  value={role}
                  checked={principal.role === role}
                  onChange={() => setRole(role)}
                />
                {role}
              </label>
            ))}
          </div>
          <div className={styles.menuDivider} />
          <div className={styles.menuNote}>
            {principal.isOperator ? "Operator principal held" : "User principal only"}. Sign-in and
            real roles arrive in B3.
          </div>
        </div>
      </details>
    </header>
  );
}

/** Role-filtered left nav (≤5 persistent sections). */
function Sidebar() {
  const { principal } = useSession();
  const items = principal ? navForRole(principal.role) : [];
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

/** The application shell: header + role-gated nav + routed content (B2). */
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
