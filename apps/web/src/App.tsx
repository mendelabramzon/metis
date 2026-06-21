import { useState } from "react";
import type { ReactNode } from "react";

import {
  Badge,
  BlockedState,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  Drawer,
  EmptyState,
  ErrorState,
  RiskBadge,
  RoutingBadge,
  ScopeBadge,
  SensitivityBadge,
} from "@/components";
import type { ActionRisk, Sensitivity } from "@/domain/types";
import { SENSITIVITY_ORDER } from "@/domain/types";

import styles from "./App.module.css";

const RISKS: ActionRisk[] = [
  "read_only",
  "reversible",
  "memory_write",
  "wiki_write",
  "external",
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {children}
    </section>
  );
}

/**
 * B1 design-system gallery. A living style guide that also doubles as the keyboard/contrast
 * verification surface for the shared primitives. The real app shell (B2) replaces this page.
 */
export function App() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <main id="main" className={styles.page}>
        <h1 className={styles.h1}>Metis design system</h1>
        <p className={styles.lede}>
          Calm, restrained primitives for the context-exoskeleton product. Status color is reserved
          for meaningful status; scope, sensitivity, and routing read as quiet labels, never alarms.
          Tab through this page — every control shows a visible focus ring.
        </p>

        <Section title="Scope & sensitivity">
          <div className={styles.label}>Workspace scope</div>
          <div className={styles.row}>
            <ScopeBadge scope="personal" />
            <ScopeBadge scope="shared" />
          </div>
          <div className={styles.label} style={{ marginTop: "var(--space-4)" }}>
            Sensitivity (floor escalates; restricted stays calm)
          </div>
          <div className={styles.row}>
            {SENSITIVITY_ORDER.map((level: Sensitivity) => (
              <SensitivityBadge key={level} level={level} />
            ))}
          </div>
        </Section>

        <Section title="Routing & risk">
          <div className={styles.label}>Routing outcome (A2 / D5)</div>
          <div className={styles.row}>
            <RoutingBadge outcome="local" />
            <RoutingBadge outcome="external" />
          </div>
          <div className={styles.label} style={{ marginTop: "var(--space-4)" }}>
            Action risk (D7)
          </div>
          <div className={styles.row}>
            {RISKS.map((risk) => (
              <RiskBadge key={risk} risk={risk} />
            ))}
          </div>
          <div className={styles.label} style={{ marginTop: "var(--space-4)" }}>
            Generic tones
          </div>
          <div className={styles.row}>
            <Badge variant="neutral">Neutral</Badge>
            <Badge variant="success">Healthy</Badge>
            <Badge variant="warning">Needs attention</Badge>
            <Badge variant="danger">Failed</Badge>
            <Badge variant="info">Syncing</Badge>
            <Badge variant="accent">New</Badge>
          </div>
        </Section>

        <Section title="Buttons">
          <div className={styles.row}>
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Remove</Button>
            <Button variant="primary" disabled>
              Disabled
            </Button>
            <Button variant="secondary" size="sm">
              Small
            </Button>
          </div>
        </Section>

        <Section title="Cards">
          <div className={styles.grid}>
            <Card>
              <CardHeader title="Pricing decision">
                <ScopeBadge scope="shared" />
              </CardHeader>
              <CardBody>
                A compact evidence card: title, trailing badges, a calm body, and a footer for
                source metadata.
              </CardBody>
              <CardFooter>
                <SensitivityBadge level="internal" />
                <span style={{ color: "var(--color-text-muted)", fontSize: "var(--text-xs)" }}>
                  acme-deck.pdf · p.4
                </span>
              </CardFooter>
            </Card>
            <Card compact>
              <CardHeader title="Onboarding doc">
                <ScopeBadge scope="personal" />
              </CardHeader>
              <CardBody>A compact card for dense lists.</CardBody>
            </Card>
          </div>
        </Section>

        <Section title="States">
          <div className={styles.stack}>
            <EmptyState
              title="No sources yet"
              description="Connect a mailbox or drop in a few documents to give this workspace something to remember."
              actions={<Button variant="primary">Add a source</Button>}
            />
            <BlockedState
              title="Kept this on-device"
              description="This question touches restricted evidence, so it was answered without an external model. You can broaden scope or ask an admin to adjust the model policy."
              actions={<Button variant="secondary">Review model policy</Button>}
            />
            <ErrorState
              title="Couldn’t reach the gateway"
              description="The request failed before it reached the workspace. Check the connection and try again."
              actions={<Button variant="secondary">Retry</Button>}
            />
          </div>
        </Section>

        <Section title="Drawer">
          <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
            Open citation drawer
          </Button>
          <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Citation">
            <Card flush>
              <CardBody>
                “We agreed to hold list price and revisit in Q3.”
              </CardBody>
              <CardFooter>
                <ScopeBadge scope="shared" />
                <SensitivityBadge level="confidential" />
              </CardFooter>
            </Card>
            <p style={{ marginTop: "var(--space-4)", color: "var(--color-text-muted)" }}>
              Focus is trapped here while open. Press Escape, click outside, or use Close — focus
              returns to the trigger.
            </p>
            <div style={{ marginTop: "var(--space-4)" }}>
              <Button variant="primary" onClick={() => setDrawerOpen(false)}>
                Done
              </Button>
            </div>
          </Drawer>
        </Section>
      </main>
    </>
  );
}
