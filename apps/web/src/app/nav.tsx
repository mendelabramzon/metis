import type { ReactNode } from "react";

import type { Role } from "@/session/types";

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: ReactNode;
  /** Roles that may see (and reach) this section. Items the role lacks are hidden from the nav. */
  allowedRoles: readonly Role[];
}

const ALL: readonly Role[] = ["owner", "admin", "member", "viewer", "auditor"];

// A tiny stroke-icon factory (no icon dependency). Lowercase + called as a function — it returns
// JSX but isn't a component, so it stays out of the nav config's exported surface.
function svgIcon(paths: ReactNode): ReactNode {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths}
    </svg>
  );
}

/**
 * The five persistent sections. Role allowlists are sensible defaults, easy to adjust as the
 * permission model firms up: everyone asks and sees activity; members+ manage sources and review;
 * Settings is for admins/owners (operator-only subsections gate further inside, per G5); an auditor
 * is scoped to Review + Activity.
 */
export const NAV: readonly NavItem[] = [
  {
    id: "ask",
    label: "Ask",
    path: "/ask",
    allowedRoles: ["owner", "admin", "member", "viewer"],
    icon: svgIcon(
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </>,
    ),
  },
  {
    id: "sources",
    label: "Sources",
    path: "/sources",
    allowedRoles: ["owner", "admin", "member"],
    icon: svgIcon(
      <>
        <path d="M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Z" />
        <path d="M4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7" />
        <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
      </>,
    ),
  },
  {
    id: "review",
    label: "Review",
    path: "/review",
    allowedRoles: ["owner", "admin", "member", "auditor"],
    icon: svgIcon(
      <>
        <path d="M9 11.5 11 13.5 15.5 9" />
        <path d="M5 4h14v16l-7-3-7 3Z" />
      </>,
    ),
  },
  {
    id: "activity",
    label: "Activity",
    path: "/activity",
    allowedRoles: ALL,
    icon: svgIcon(<path d="M3 12h4l2 6 4-14 2 8h6" />),
  },
  {
    id: "settings",
    label: "Settings",
    path: "/settings",
    allowedRoles: ["owner", "admin"],
    icon: svgIcon(
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" />
      </>,
    ),
  },
];

export function navForRole(role: Role): NavItem[] {
  return NAV.filter((item) => item.allowedRoles.includes(role));
}
