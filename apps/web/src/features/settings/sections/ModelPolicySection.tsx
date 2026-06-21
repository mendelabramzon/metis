import { EmptyState } from "@/components";

import { SectionHeader } from "./SectionHeader";

/** Model policy (G1 stub; G4 fills: external-allowed toggle + spend caps + read spend). */
export function ModelPolicySection() {
  return (
    <>
      <SectionHeader title="Model policy" lede="Whether external models may see this workspace's data, plus spend caps." />
      <EmptyState title="Model policy arrives in G4" description="The external-models toggle, spend caps, and current spend land here." />
    </>
  );
}
