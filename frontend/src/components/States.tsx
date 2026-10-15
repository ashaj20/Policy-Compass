import type { ReactNode } from "react";
import { Button } from "./Button";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="pc-state" role="status" aria-live="polite">
      <span className="pc-spinner pc-spinner--lg" aria-hidden="true" />
      <p className="pc-state__text">{label}</p>
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="pc-skeleton" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="pc-skeleton__line" />
      ))}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="pc-state pc-state--empty">
      <h2 className="pc-state__title">{title}</h2>
      {description && <p className="pc-state__text">{description}</p>}
      {action}
    </div>
  );
}

interface ErrorStateProps {
  message?: string;
  errorId?: string;
  onRetry?: () => void;
  onBack?: () => void;
}

export function ErrorState({
  message = "Something went wrong. Please try again.",
  errorId,
  onRetry,
  onBack,
}: ErrorStateProps) {
  return (
    <div className="pc-state pc-state--error" role="alert">
      <h2 className="pc-state__title">{message}</h2>
      {errorId && <p className="pc-state__ref">Reference: {errorId}</p>}
      <div className="pc-state__actions">
        {onRetry && <Button onClick={onRetry}>Try again</Button>}
        {onBack && (
          <Button variant="secondary" onClick={onBack}>
            Go back
          </Button>
        )}
      </div>
    </div>
  );
}
