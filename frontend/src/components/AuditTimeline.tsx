import { describeEvent, formatTimestamp, type AuditEvent as AuditEventData } from "../lib/audit";

export function AuditEvent({ event }: { event: AuditEventData }) {
  const { summary, changes } = describeEvent(event);
  return (
    <li className="pc-audit__event">
      <span className="pc-audit__dot" aria-hidden="true" />
      <div className="pc-audit__body">
        <p className="pc-audit__summary">
          <strong>{event.actor ?? "System"}</strong> {summary}
        </p>
        {changes.length > 0 && (
          <ul className="pc-audit__changes">
            {changes.map((c) => (
              <li key={c.label}>
                <span className="pc-audit__field">{c.label}:</span> <del>{c.from}</del>{" "}
                <span aria-hidden="true">→</span>
                <span className="visually-hidden"> changed to </span> <ins>{c.to}</ins>
              </li>
            ))}
          </ul>
        )}
        <time className="pc-audit__time" dateTime={event.timestamp}>
          {formatTimestamp(event.timestamp)}
        </time>
      </div>
    </li>
  );
}

/** Newest-first list of audit events. */
export function AuditTimeline({ events }: { events: AuditEventData[] }) {
  return (
    <ol className="pc-audit" aria-label="Activity, newest first">
      {events.map((e) => (
        <AuditEvent key={e.id} event={e} />
      ))}
    </ol>
  );
}
