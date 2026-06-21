import { EmptyState } from "@/components";

import { SectionHeader } from "./SectionHeader";

/** Operations (G1 stub, operator-only; G5 fills: health, failed jobs, providers, audit, backups). */
export function OperationsSection() {
  return (
    <>
      <SectionHeader title="Operations" lede="Operator-only: deployment health, jobs, providers, and audit." />
      <EmptyState title="Operations arrives in G5" description="A health dashboard, failed-job drilldown, provider config, and audit search land here." />
    </>
  );
}
