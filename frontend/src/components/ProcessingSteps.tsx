const STEPS = ["Uploading", "Document processing", "Building knowledge", "Making searchable"];

/** Which step is under way for each backend processing stage (US-011/012). */
const CURRENT_STEP: Record<string, number> = {
  QUEUED: 1,
  EXTRACTING: 1,
  CHUNKING: 1,
  INDEXING: 2,
  VALIDATING: 3,
  DONE: 4,
};

interface ProcessingStepsProps {
  stage?: string | null;
  failed?: boolean;
}

/**
 * Processing progress as in the design: Uploading ✓ / Document processing ✓ / Building
 * knowledge ● / Making searchable ○. Each step says its state in words for screen readers.
 */
export function ProcessingSteps({ stage, failed = false }: ProcessingStepsProps) {
  const current = CURRENT_STEP[stage ?? "QUEUED"] ?? 1;
  return (
    <ol className="pc-steps-progress" aria-label="Processing progress">
      {STEPS.map((label, index) => {
        const state =
          index < current ? "done" : index === current ? (failed ? "failed" : "current") : "pending";
        const icon = { done: "✓", current: "●", pending: "○", failed: "✕" }[state];
        const spoken = { done: "complete", current: "in progress", pending: "not started", failed: "failed" }[state];
        return (
          <li key={label} className={`pc-steps-progress__item pc-steps-progress__item--${state}`}>
            <span className="pc-steps-progress__label">{label}</span>
            <span className="pc-steps-progress__icon" aria-hidden="true">
              {icon}
            </span>
            <span className="visually-hidden"> — {spoken}</span>
          </li>
        );
      })}
    </ol>
  );
}
