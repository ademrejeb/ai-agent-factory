import type { ReactNode } from "react";

import { titleCase } from "@/lib/format";

export type BadgeTone = "success" | "danger" | "warning" | "info" | "neutral" | "accent";

const SUCCESS = new Set([
  "completed",
  "published",
  "monitored",
  "healthy",
  "connected",
  "active",
  "validated",
]);
const WARNING = new Set(["configured", "tested", "connected_limited", "degraded"]);
const DANGER = new Set([
  "failed",
  "error",
  "unhealthy",
  "revoked",
  "deactivated",
  "superseded",
  "not_ready",
]);
const ACCENT = new Set(["draft"]);

export function statusTone(status: string | null | undefined): BadgeTone {
  if (!status) return "neutral";
  const normalized = status.toLowerCase();
  if (SUCCESS.has(normalized)) return "success";
  if (WARNING.has(normalized)) return "warning";
  if (DANGER.has(normalized)) return "danger";
  if (ACCENT.has(normalized)) return "accent";
  return "neutral";
}

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
  title?: string;
}

export function Badge({ children, tone = "neutral", dot = false, title }: BadgeProps) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {dot ? <span className="badge-dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function StatusBadge({ status, label }: { status: string | null | undefined; label?: string }) {
  return (
    <Badge tone={statusTone(status)} dot>
      {label ?? titleCase(status ?? "unknown")}
    </Badge>
  );
}
