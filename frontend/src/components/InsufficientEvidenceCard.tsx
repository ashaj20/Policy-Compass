import type { ReactNode } from "react";
import { routeHref } from "../lib/contacts";
import type { Answer } from "../lib/questions";

// Why we couldn't answer, when it isn't simply missing information.
const REASON_NOTES: Record<string, string> = {
  conflict: "The approved policies contain conflicting information on this.",
  limit_reached: "Today's answer limit has been reached. Please try again tomorrow.",
  unavailable: "Answering is temporarily unavailable. Please try again shortly.",
};

const HELP_ACTIONS: Record<string, string> = {
  EMAIL: "Send an email",
  PHONE: "Call",
  WEBSITE: "Visit Help Centre",
  CONTACT_FORM: "Open contact form",
  HELPDESK: "Visit Help Centre",
};

/**
 * Shown when there isn't enough approved evidence to answer (US-017). Staff are pointed to the
 * policy owner; the public only ever see a public help route. With no contact configured we show
 * the generic message and never invent one.
 */
export function InsufficientEvidenceCard({
  answer,
  audience,
  noContactHint,
}: {
  answer: Pick<Answer, "id" | "question" | "reason" | "escalation">;
  audience: "internal" | "public";
  /** Extra guidance when no contact is configured, e.g. a link for administrators. */
  noContactHint?: ReactNode;
}) {
  // Belt and braces: an internal owner is never shown on a public card, whatever the server sent.
  const contact = audience === "public" && answer.escalation?.kind === "owner" ? null : answer.escalation;
  const note = answer.reason ? REASON_NOTES[answer.reason] : undefined;
  const policies = audience === "internal" ? "the approved policies" : "our approved policies";

  return (
    <article className="pc-insufficient" aria-labelledby={`insufficient-${answer.id}`}>
      <p className="pc-answer__question">
        <span className="pc-answer__kicker">Your question</span>
        {answer.question}
      </p>
      <div className="pc-insufficient__body">
        <h2 id={`insufficient-${answer.id}`} className="pc-answer__heading">
          {contact
            ? `We couldn't find enough information in ${policies} to answer this.`
            : "We couldn't find enough information to answer this."}
        </h2>
        {note && <p className="pc-insufficient__note">{note}</p>}

        {contact?.kind === "owner" && (
          <section className="pc-escalation" aria-label="Policy owner">
            <h3 className="pc-answer__heading pc-answer__heading--small">Policy owner</h3>
            <p className="pc-contact__name">{contact.name}</p>
            {contact.job_title && <p className="pc-contact__meta">{contact.job_title}</p>}
            {contact.email && (
              <p className="pc-contact__meta">
                <a href={`mailto:${contact.email}`}>{contact.email}</a>
              </p>
            )}
            {contact.phone && (
              <p className="pc-contact__meta">
                <a href={`tel:${contact.phone.replace(/[^0-9+]/g, "")}`}>{contact.phone}</a>
              </p>
            )}
            <p className="pc-field__hint">Responsible for the {contact.policy_name}.</p>
            {contact.email && (
              <a className="pc-button pc-button--primary" href={`mailto:${contact.email}?subject=${encodeURIComponent(`Policy question: ${answer.question.slice(0, 120)}`)}`}>
                Contact policy owner
              </a>
            )}
          </section>
        )}

        {contact?.kind === "help_route" && (
          <section className="pc-escalation" aria-label="Need help?">
            <h3 className="pc-answer__heading pc-answer__heading--small">Need help?</h3>
            <p className="pc-contact__name">{contact.label}</p>
            {contact.description && <p className="pc-contact__meta">{contact.description}</p>}
            <p className="pc-contact__meta">{contact.destination}</p>
            <a className="pc-button pc-button--primary" href={routeHref(contact)} rel="noopener noreferrer">
              {HELP_ACTIONS[contact.route_type] ?? "Get help"}
            </a>
          </section>
        )}

        {!contact && (
          <>
            <p>
              {audience === "internal"
                ? "No policy owner has been set up for this topic yet. Please check with your manager."
                : "Please contact the organisation through its main customer support channel."}
            </p>
            {noContactHint}
          </>
        )}
      </div>
    </article>
  );
}
