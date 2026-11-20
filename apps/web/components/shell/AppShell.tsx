"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "@/components/providers/AuthProvider";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Logo } from "@/components/ui/Logo";

import styles from "./AppShell.module.css";

const PLATFORM_NAME = process.env.NEXT_PUBLIC_PLATFORM_NAME ?? "AI Agent Factory";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  exact?: boolean;
}

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Build",
    items: [
      { href: "/overview", label: "Overview", icon: "grid", exact: true },
      { href: "/agents", label: "Agents", icon: "bot" },
      { href: "/tools", label: "Tools & MCP", icon: "terminal" },
      { href: "/skills", label: "Skills", icon: "shield" },
      { href: "/runs", label: "Runs", icon: "play" },
    ],
  },
  {
    label: "Connect",
    items: [
      { href: "/providers", label: "Model providers", icon: "plug" },
      { href: "/credentials", label: "API keys", icon: "key" },
      { href: "/workspaces", label: "Workspaces", icon: "layers" },
    ],
  },
  {
    label: "Platform",
    items: [
      { href: "/docs", label: "API reference", icon: "book" },
      { href: "/settings", label: "Settings", icon: "settings" },
    ],
  },
];

const TITLES: Array<[string, string]> = [
  ["/agents/new", "New agent"],
  ["/agents", "Agents"],
  ["/runs", "Runs"],
  ["/tools", "Tools & MCP"],
  ["/skills", "Skills"],
  ["/providers", "Model providers"],
  ["/credentials", "API keys"],
  ["/workspaces", "Workspaces"],
  ["/docs", "API reference"],
  ["/settings", "Settings"],
  ["/overview", "Overview"],
];

function sectionTitle(pathname: string): string {
  const match = TITLES.find(
    ([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  return match?.[1] ?? "Overview";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, loading, logout, switchTenant } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isAuthRoute = pathname === "/login" || pathname === "/register";
  const isPublicRoute = isAuthRoute || pathname === "/";

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!loading && !me && !isPublicRoute) {
      const next = encodeURIComponent(pathname);
      router.replace(`/login?next=${next}`);
    }
  }, [loading, me, isPublicRoute, pathname, router]);

  if (isPublicRoute) return <>{children}</>;

  if (loading) {
    return (
      <div className={styles.boot}>
        <Logo size={46} />
        <span className={styles.bootText}>Connecting to the control plane…</span>
      </div>
    );
  }

  if (!me) return null;

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);

  // The overview, catalog, and new-agent pages already carry a primary
  // "New agent" action. Repeating it in the top bar looks like two competing
  // calls to action, so the global shortcut is hidden there.
  const showGlobalCreate = !["/overview", "/agents", "/agents/new"].includes(pathname);

  return (
    <div className={styles.shell}>
      <aside className={`${styles.sidebar} ${mobileOpen ? styles.sidebarOpen : ""}`}>
        <Link href="/overview" className={styles.brand}>
          <Logo size={34} />
          <div>
            <span className={styles.brandName}>{PLATFORM_NAME}</span>
            <span className={styles.brandMeta}>Agent control plane</span>
          </div>
        </Link>

        <nav className={styles.nav} aria-label="Primary">
          {NAV_GROUPS.map((group) => (
            <div className={styles.navGroup} key={group.label}>
              <span className={styles.navLabel}>{group.label}</span>
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`${styles.navItem} ${isActive(item) ? styles.navItemActive : ""}`}
                  aria-current={isActive(item) ? "page" : undefined}
                >
                  <Icon name={item.icon} size={17} />
                  <span>{item.label}</span>
                </Link>
              ))}
            </div>
          ))}
        </nav>

        <div className={styles.sidebarFooter}>
          <div className={styles.orgCard}>
            <span className={styles.orgAvatar}>
              {me.organization?.name?.slice(0, 1).toUpperCase() ?? "?"}
            </span>
            <div className={styles.orgText}>
              {(me.organizations?.length ?? 0) > 1 ? (
                <select
                  className="tenantSelect"
                  aria-label="Active tenant"
                  value={me.organization?.id ?? ""}
                  onChange={(event) => void switchTenant(event.target.value)}
                >
                  {(me.organizations ?? []).map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.name} · {org.role}
                    </option>
                  ))}
                </select>
              ) : (
                <span className={styles.orgName}>{me.organization?.name ?? "No organization"}</span>
              )}
              <span className={styles.orgRole}>{me.role ?? "member"} · {me.user.email}</span>
            </div>
            <button
              type="button"
              className={styles.logout}
              onClick={() => void logout()}
              aria-label="Sign out"
              title="Sign out"
            >
              <Icon name="logout" size={17} />
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen ? (
        <button
          type="button"
          className={styles.scrim}
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <div className={styles.main}>
        <header className={styles.topbar}>
          <button
            type="button"
            className={styles.menuButton}
            onClick={() => setMobileOpen((open) => !open)}
            aria-label="Toggle navigation"
            aria-expanded={mobileOpen}
          >
            <Icon name={mobileOpen ? "close" : "menu"} size={20} />
          </button>
          <div className={styles.crumbs}>
            <span className={styles.crumbRoot}>Control plane</span>
            <Icon name="chevron-right" size={14} />
            <span className={styles.crumbCurrent}>{sectionTitle(pathname)}</span>
          </div>
          <div className={styles.topbarActions}>
            <Link href="/docs" className={styles.topbarLink}>
              <Icon name="terminal" size={16} />
              <span>API</span>
            </Link>
            {showGlobalCreate ? (
              <Link href="/agents/new" className={styles.topbarCta}>
                <Icon name="plus" size={16} />
                <span>New agent</span>
              </Link>
            ) : null}
          </div>
        </header>
        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}
