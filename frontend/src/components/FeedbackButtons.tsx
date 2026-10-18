import { useId, useState } from "react";
import { FEEDBACK_REASONS, type Feedback, type FeedbackReason } from "../lib/questions";

interface FeedbackButtonsProps {
  initial?: Feedback | null;
  /** Saves the feedback; rejects if it couldn't be saved. */
  onSubmit: (helpful: boolean, reason: FeedbackReason | null) => Promise<void>;
}

/**
 * "Was this answer helpful?" (US-020). A "No" optionally asks why. Feedback is only stored for
 * administrators to review; it never changes policies or answers.
 */
export function FeedbackButtons({ initial, onSubmit }: FeedbackButtonsProps) {
  const id = useId();
  const [current, setCurrent] = useState<Feedback | null>(initial ?? null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  async function save(helpful: boolean, reason: FeedbackReason | null) {
    setSaving(true);
    setFailed(false);
    const previous = current;
    setCurrent({ helpful, reason });
    try {
      await onSubmit(helpful, reason);
    } catch {
      setCurrent(previous);
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="pc-feedback" aria-label="Feedback">
      <div className="pc-feedback__row">
        <span className="pc-feedback__question" id={`${id}-question`}>
          Was this answer helpful?
        </span>
        <div role="group" aria-labelledby={`${id}-question`} className="pc-feedback__buttons">
          <button
            type="button"
            className="pc-chip"
            aria-pressed={current?.helpful === true}
            disabled={saving}
            onClick={() => save(true, null)}
          >
            Yes
          </button>
          <button
            type="button"
            className="pc-chip"
            aria-pressed={current?.helpful === false}
            disabled={saving}
            onClick={() => save(false, null)}
          >
            No
          </button>
        </div>
      </div>

      {current?.helpful === false && (
        <fieldset className="pc-feedback__reasons" disabled={saving}>
          <legend className="pc-field__hint">What went wrong? (optional)</legend>
          {FEEDBACK_REASONS.map((r) => (
            <label key={r.value} className="pc-radio">
              <input
                type="radio"
                name={`${id}-reason`}
                value={r.value}
                checked={current.reason === r.value}
                onChange={() => save(false, r.value)}
              />
              {r.label}
            </label>
          ))}
        </fieldset>
      )}

      <p className="pc-field__hint" role="status">
        {failed ? "We couldn't save your feedback. Please try again." : current ? "Thanks for your feedback." : ""}
      </p>
    </section>
  );
}
