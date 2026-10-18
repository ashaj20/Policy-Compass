import { formatLongDate } from "../lib/format";
import type { Answer, Citation } from "../lib/questions";

/** One source an answer relied on: policy, version, section and effective date. */
export function CitationCard({ citation }: { citation: Citation }) {
  return (
    <li className="pc-citation">
      <p className="pc-citation__policy">{citation.policy_name}</p>
      <p className="pc-citation__meta">
        Version {citation.version_label} · Effective {formatLongDate(citation.effective_date)}
      </p>
      {citation.section && <p className="pc-citation__section">Section: {citation.section}</p>}
    </li>
  );
}

/**
 * A grounded answer (US-016). The answer and its sources are visually distinct (UX brief §12),
 * and only sources that actually supported the answer are listed.
 */
export function AnswerCard({ answer }: { answer: Answer }) {
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
        <p className="pc-answer__basis">Based only on your organisation's approved policies.</p>
      </section>
      <section className="pc-answer__sources" aria-labelledby={`sources-${answer.id}`}>
        <h3 id={`sources-${answer.id}`} className="pc-answer__heading pc-answer__heading--small">
          Sources
        </h3>
        <ul className="pc-citations">
          {answer.citations.map((c, i) => (
            <CitationCard key={`${c.version_id}-${c.section}-${i}`} citation={c} />
          ))}
        </ul>
      </section>
    </article>
  );
}
