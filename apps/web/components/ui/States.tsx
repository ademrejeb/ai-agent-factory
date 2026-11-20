import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: IconName;
  compact?: boolean;
}

export function EmptyState({
  title,
  description,
  action,
  icon = "layers",
  compact = false,
}: EmptyStateProps) {
  return (
    <div className={`empty ${compact ? "empty-compact" : ""}`}>
      <span className="empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function LoadingBlock({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="loading-block" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton-row" style={{ animationDelay: `${index * 90}ms` }} />
      ))}
    </div>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-block" role="alert">
      <Icon name="alert" size={18} />
      <div>
        <strong>Could not load this data</strong>
        <p>{message}</p>
      </div>
      {onRetry ? (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <div className="inline-error" role="alert">
      <Icon name="alert" size={16} />
      <span>{message}</span>
    </div>
  );
}
