import { EmptyState } from "@/components";

import { SectionHeader } from "./SectionHeader";

/** Permissions (G1 stub; G3 fills: per-source permission + workspace sensitivity defaults). */
export function PermissionsSection() {
  return (
    <>
      <SectionHeader title="Permissions" lede="Per-source permissions and the workspace's sensitivity defaults." />
      <EmptyState title="Permissions arrive in G3" description="Source permissions and sensitivity defaults land here." />
    </>
  );
}
