"use client";

import Link from "next/link";

import { useAuth } from "@/components/providers/AuthProvider";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Logo } from "@/components/ui/Logo";

import styles from "./landing.module.css";

const PLATFORM_NAME = process.env.NEXT_PUBLIC_PLATFORM_NAME ?? "AI Agent Factory";

const FEATURES: Array<{ icon: IconName; title: string; copy: string }> = [
  {
    icon: "bot",
    title: "One agent catalog",
    copy: "Describe the agent once, then run a platform-owned graph against a real model. Tools, skills, and guardrails are attached to the agent, not buried in prompt text.",
  },
  {
    icon: "workflow",
    title: "Graphs that do real work",
    copy: "Compose agent loops, tool calls, HTTP steps, conditions, and guardrails. Every branch is visible and every failure is recorded.",
  },
  {
    icon: "plug",
    title: "Bring your own tools",
    copy: "Register HTTP tools and MCP servers once, then attach them to agent nodes. Headers are encrypted server-side and never returned.",
  },
  {
    icon: "key",
    title: "A stable gateway",
    copy: "Issue scoped customer keys, stream with SSE, and return the same contract to every app. Blocking and streaming are real; nothing is faked.",
  },
  {
    icon: "shield",
    title: "Tenant isolation",
    copy: "Every resource is resolved from the signed-in organization. Agent ids, runs, and keys are never accepted across tenants.",
  },
  {
    icon: "play",
    title: "Runs you can prove",
    copy: "Every test and gateway call is recorded with duration, tokens, status, and the failing node. Errors are explained in plain language, not just a code.",
  },
];

const STEPS = [
  {
    title: "Connect a model endpoint",
    copy: "Use local Ollama or any OpenAI-compatible endpoint. The platform verifies GET /models and shows the models it actually found.",
  },
  {
    title: "Compose the agent",
    copy: "Start blank or from a template. Build a real graph, test it against your endpoint, then publish a version.",
  },
  {
    title: "Call it from your apps",
    copy: "Create a scoped API key and call one gateway from ticketing, support, ops, or any other product you run.",
  },
];

export default function LandingPage() {
  const { me, loading } = useAuth();
  const signedIn = !loading && Boolean(me);

  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <Link href="/" className={styles.brand}>
            <Logo size={34} />
            <span className={styles.brandText}>
              <span className={styles.brandName}>{PLATFORM_NAME}</span>
              <span className={styles.brandTag}>Agent control plane</span>
            </span>
          </Link>
          <nav className={styles.navLinks} aria-label="Product">
            <a href="#product" className={styles.navLink}>
              Product
            </a>
            <a href="#how" className={styles.navLink}>
              How it works
            </a>
            <a href="#dispatch" className={styles.navLink}>
              Dispatch
            </a>
            <a href="#security" className={styles.navLink}>
              Security
            </a>
            <Link href="/docs" className={styles.navLink}>
              Docs
            </Link>
          </nav>
          <div className={styles.navActions}>
            {signedIn ? (
              <Link href="/overview" className={styles.primaryLink}>
                Open console
                <Icon name="arrow-up-right" size={14} />
              </Link>
            ) : (
              <>
                <Link href="/login" className={styles.ghostLink}>
                  Sign in
                </Link>
                <Link href="/register" className={styles.primaryLink}>
                  Start free
                  <Icon name="arrow-up-right" size={14} />
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main className={styles.shell}>
        <section className={styles.hero}>
          <span className={styles.eyebrow}>
            <span className={styles.dot} />
            Production control plane
          </span>
          <h1>
            Ship AI agents
            <br />
            <span className={styles.gradient}>without rebuilding the platform.</span>
          </h1>
          <p className={styles.sub}>
            {PLATFORM_NAME} gives every application you run one place to create agents, connect
            real models, publish versions, and call them through a stable gateway. Built for
            operators, not demos.
          </p>
          <div className={styles.heroActions}>
            <Link href={signedIn ? "/overview" : "/register"} className={styles.primaryLink}>
              {signedIn ? "Open the console" : "Create an organization"}
              <Icon name="arrow-up-right" size={14} />
            </Link>
            <a href="#dispatch" className={styles.secondaryLink}>
              See the ticketing dispatcher
              <Icon name="chevron-right" size={14} />
            </a>
          </div>
          <div className={styles.proof}>
            <span>
              <Icon name="check" size={13} /> Real provider checks
            </span>
            <span>
              <Icon name="check" size={13} /> Encrypted credentials
            </span>
            <span>
              <Icon name="check" size={13} /> Durable run history
            </span>
            <span>
              <Icon name="check" size={13} /> No fake execution path
            </span>
          </div>
        </section>

        <section className={styles.mockup} aria-label="Product preview">
          <div className={styles.windowBar}>
            <i />
            <i />
            <i />
            <span className={styles.windowTitle}>console · agents / field dispatch</span>
          </div>
          <div className={styles.mockBody}>
            <aside className={styles.mockSide}>
              <div className={styles.mockBrand}>
                <Logo size={20} />
                {PLATFORM_NAME}
              </div>
              <div className={styles.mockNav}>
                <span>Overview</span>
                <span className={styles.active}>Agents</span>
                <span>Runs</span>
                <span>Providers</span>
                <span>API keys</span>
                <span>Workspaces</span>
              </div>
            </aside>
            <div className={styles.mockMain}>
              <div className={styles.mockTop}>
                <div>
                  <h3>Agents</h3>
                  <span>Published, tested, and monitored</span>
                </div>
                <span className={styles.pill + " " + styles.pillBlue}>2 active</span>
              </div>
              <div className={styles.mockStats}>
                <div className={styles.mockStat}>
                  <b>1,284</b>
                  <span>runs this week</span>
                </div>
                <div className={styles.mockStat}>
                  <b>98.6%</b>
                  <span>completed</span>
                </div>
                <div className={styles.mockStat}>
                  <b>812 ms</b>
                  <span>p50 latency</span>
                </div>
              </div>
              <div className={styles.mockRows}>
                <div className={styles.mockRow}>
                  <div>
                    <strong>Field dispatch</strong>
                    <small>LangGraph · ticket routing</small>
                  </div>
                  <span className={styles.pill + " " + styles.pillGreen}>Monitored</span>
                  <span>v4</span>
                </div>
                <div className={styles.mockRow}>
                  <div>
                    <strong>Support triage</strong>
                    <small>Agent · tools + MCP</small>
                  </div>
                  <span className={styles.pill + " " + styles.pillGreen}>Published</span>
                  <span>v2</span>
                </div>
                <div className={styles.mockRow}>
                  <div>
                    <strong>Invoice explainer</strong>
                    <small>LangGraph · draft</small>
                  </div>
                  <span className={styles.pill + " " + styles.pillAmber}>Configured</span>
                  <span>v1</span>
                </div>
              </div>
            </div>
          </div>
          <p className={styles.mockCaption}>
            Illustrative interface. Every number in the product comes from your own recorded runs.
          </p>
        </section>

        <section className={styles.section} id="product">
          <div className={styles.sectionHead}>
            <h2>Control the full lifecycle, not just the prompt.</h2>
            <p>
              A logical agent is separate from the engine that executes it. Link it to a real
              provider, test it, publish an immutable version, and keep every run for diagnosis.
            </p>
          </div>
          <div className={styles.grid}>
            {FEATURES.map((feature) => (
              <div key={feature.title} className={styles.feature}>
                <span className={styles.featureIcon}>
                  <Icon name={feature.icon} size={17} />
                </span>
                <h3>{feature.title}</h3>
                <p>{feature.copy}</p>
              </div>
            ))}
          </div>
          <div className={styles.engines} aria-label="Supported engines">
            <span className={styles.engine}>LangGraph runtime</span>
            <span className={styles.engine}>HTTP tools</span>
            <span className={styles.engine}>MCP servers</span>
            <span className={styles.engine}>Skills</span>
            <span className={styles.engine}>Guardrails</span>
            <span className={styles.engine}>Ollama · LM Studio · vLLM</span>
          </div>
        </section>

        <section className={styles.section} id="how">
          <div className={styles.sectionHead}>
            <h2>From a model endpoint to a callable agent.</h2>
            <p>
              No fake provider, no hidden demo. The platform verifies what it can and records what
              happens.
            </p>
          </div>
          <div className={styles.steps}>
            {STEPS.map((step, index) => (
              <div className={styles.step} key={step.title}>
                <span className={styles.stepNum}>{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.copy}</p>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.section + " " + styles.split} id="dispatch">
          <div className={styles.splitCopy}>
            <span className={styles.eyebrow}>In production</span>
            <h2 style={{ marginTop: 18 }}>A dispatcher that reads the workshop, not a form.</h2>
            <p>
              The ticketing agent receives a real ticket, loads live technician metrics, and
              chooses one worker. The ticketing service validates the choice before it creates a
              work order.
            </p>
            <ul className={styles.checklist}>
              <li>
                <Icon name="check" size={14} />
                Skills, certifications, live GPS, ETA, current load, rating and resolution history.
              </li>
              <li>
                <Icon name="check" size={14} />
                Encrypted shared secret between the agent and the ticketing API.
              </li>
              <li>
                <Icon name="check" size={14} />
                Strict JSON decision; unknown or ineligible technician ids are rejected.
              </li>
              <li>
                <Icon name="check" size={14} />
                Deterministic ranking remains the fallback when the model is slow or unavailable.
              </li>
            </ul>
          </div>
          <div className={styles.decisionCard} aria-label="Dispatch decision preview">
            <div className={styles.decisionTop}>
              <div>
                <strong>VRV — surcharge / débit faible</strong>
                <span style={{ display: "block" }}>TK-2026-0002 · P2 high · SLA 8h</span>
              </div>
              <span className={styles.pill + " " + styles.pillBlue}>AI dispatch</span>
            </div>
            <div className={styles.tech}>
              <span className={styles.techAvatar}>MB</span>
              <div className={styles.techBody}>
                <strong>Mehdi Bennani</strong>
                <small>HVAC_VRV · 0.6 km · ~5 min · 1 active job</small>
              </div>
              <span className={styles.techScore}>75.6</span>
            </div>
            <div className={styles.tech}>
              <span className={styles.techAvatar}>YA</span>
              <div className={styles.techBody}>
                <strong>Yassine El Amrani</strong>
                <small>Elevator · 2.3 km · ~6 min · missing HVAC skill</small>
              </div>
              <span className={styles.techScore} style={{ color: "var(--faint)" }}>
                41.8
              </span>
            </div>
            <div className={styles.tech}>
              <span className={styles.techAvatar}>KT</span>
              <div className={styles.techBody}>
                <strong>Khadija Tazi</strong>
                <small>Security · 1652 km · no location refresh</small>
              </div>
              <span className={styles.techScore} style={{ color: "var(--faint)" }}>
                25.7
              </span>
            </div>
            <div className={styles.decisionNote}>
              Selected Mehdi Bennani for the HVAC skill match and five-minute ETA. Work order
              created, technician assigned, audit event recorded.
            </div>
          </div>
        </section>

        <section className={styles.securityBand} id="security">
          <h2>Operational safety is part of the product.</h2>
          <div className={styles.securityGrid}>
            <div className={styles.securityItem}>
              <strong>Encrypted at rest</strong>
              <p>Provider and agent secrets use Fernet; values never return through the API.</p>
            </div>
            <div className={styles.securityItem}>
              <strong>Scoped keys</strong>
              <p>Customer credentials carry <code className="mono">agents:run</code> or read-only run access.</p>
            </div>
            <div className={styles.securityItem}>
              <strong>Outbound policy</strong>
              <p>Private and metadata targets are blocked unless explicitly allowed.</p>
            </div>
            <div className={styles.securityItem}>
              <strong>Bounded execution</strong>
              <p>Body, response, message and provider-extension limits protect memory and logs.</p>
            </div>
          </div>
        </section>

        <section className={styles.cta}>
          <div>
            <h2>Give every product one agent layer.</h2>
            <p>Create an organization, connect a model, and ship the first agent today.</p>
          </div>
          <div className={styles.heroActions} style={{ marginTop: 0 }}>
            <Link href={signedIn ? "/overview" : "/register"} className={styles.primaryLink}>
              {signedIn ? "Open the console" : "Start free"}
              <Icon name="arrow-up-right" size={14} />
            </Link>
            <Link href="/login" className={styles.secondaryLink}>
              Sign in
            </Link>
          </div>
        </section>

        <footer className={styles.footer}>
          <span>
            © {new Date().getFullYear()} {PLATFORM_NAME}. Self-hosted.
          </span>
          <div className={styles.footerLinks}>
            <Link href="/docs">API reference</Link>
            <Link href="/login">Sign in</Link>
            <a href="#product">Product</a>
          </div>
        </footer>
      </main>
    </div>
  );
}
