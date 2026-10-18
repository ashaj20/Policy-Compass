import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { formatLongDate } from "../lib/format";
import type { PublicCitation } from "../lib/questions";

/**
 * One source an answer relied on (US-018): policy, version, section and effective date. Opening
 * it shows the exact passage that was used, so people can check the answer for themselves.
 */
export function CitationCard({ citation, policyHref }: { citation: PublicCitation; policyHref?: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const where = [citation.section && `Section: ${citation.section}`, citation.page && `Page ${citation.page}`]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="pc-citation">
      <button
        type="button"
        className="pc-citation__toggle"
        aria-expanded={open}
        aria-controls={`${id}-source`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="pc-citation__policy">{citation.policy_name}</span>
        <span className="pc-citation__meta">
          Version {citation.version_label} · Effective {formatLongDate(citation.effective_date)}
        </span>
        {where && <span className="pc-citation__section">{where}</span>}
        <span className="pc-citation__action">{open ? "Hide source" : "View source"}</span>
      </button>
      <div id={`${id}-source`} className="pc-citation__source" hidden={!open}>
        <p className="pc-field__hint">The passage this answer used:</p>
        <blockquote className="pc-citation__excerpt">{citation.excerpt}</blockquote>
        {policyHref && <Link to={policyHref}>Open the {citation.policy_name}</Link>}
      </div>
    </li>
  );
}

/**
 * A grounded answer (US-016). The answer and its sources are visually distinct (UX brief §12),
 * and only sources that actually supported the answer are listed.
 */
export function AnswerCard<C extends PublicCitation>({
  answer,
  policyHref,
  basis = "Based only on your organisation's approved policies.",
  footer,
}: {
  answer: { id: string; question: string; answer: string | null; citations: C[] };
  /** Where a source's policy can be opened (internal only; the public get the excerpt). */
  policyHref?: (citation: C) => string;
  basis?: string;
  footer?: ReactNode;
}) {
  return (
    <article className="pc-answer" aria-labelledby={`answer-${answer.id}`}>
      <p className="pc-answer__question">
        <span className="pc-answer__kicker">Your question</span>
        {answer.question}
      </p>
      <section className="pc-answer__body" aria-labelledby={`answer-${answer.id}`}>
        <h2 id={`answer-${answer.id}`} className="pc-answer__heading">
          Answer
        </h2>
        <p className="pc-answer__text">{answer.answer}</p>
        <p className="pc-answer__basis">{basis}</p>
      </section>
      <section className="pc-answer__sources" aria-labelledby={`sources-${answer.id}`}>
        <h3 id={`sources-${answer.id}`} className="pc-answer__heading pc-answer__heading--small">
          Sources
        </h3>
        <ul className="pc-citations">
          {answer.citations.map((c, i) => (
            <CitationCard key={`${c.policy_name}-${c.version_label}-${c.section}-${i}`} citation={c} policyHref={policyHref?.(c)} />
          ))}
        </ul>
      </section>
      {footer}
    </article>
  );
}
