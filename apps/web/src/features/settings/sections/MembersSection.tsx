import { EmptyState } from "@/components";

import { SectionHeader } from "./SectionHeader";

/** Members (G1 stub; G2 fills: invite link, list, remove, role assignment). */
export function MembersSection() {
  return (
    <>
      <SectionHeader title="Members" lede="Invite people, set roles, and manage who can access this workspace." />
      <EmptyState title="Member management arrives in G2" description="Invite links, the member list, and role assignment land next." />
    </>
  );
}
