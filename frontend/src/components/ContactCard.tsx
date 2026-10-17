import type { ReactNode } from "react";
import { routeHref, routeTypeLabel, type HelpRoute, type PolicyOwner } from "../lib/contacts";

/** An internal policy owner. Never shown on public pages. */
export function ContactCard({ owner, actions }: { owner: PolicyOwner; actions?: ReactNode }) {
  return (
    <div className="pc-contact">
      <div className="pc-contact__body">
        <p className="pc-contact__name">{owner.name}</p>
        {owner.job_title && <p className="pc-contact__meta">{owner.job_title}</p>}
        {owner.email && (
          <p className="pc-contact__meta">
            <a href={`mailto:${owner.email}`}>{owner.email}</a>
          </p>
        )}
        {owner.phone && (
          <p className="pc-contact__meta">
            <a href={`tel:${owner.phone.replace(/[^0-9+]/g, "")}`}>{owner.phone}</a>
          </p>
        )}
      </div>
      {actions && <div className="pc-contact__actions">{actions}</div>}
    </div>
  );
}

/** A public help route: how members of the public can get help. */
export function HelpRouteCard({ route, actions }: { route: HelpRoute; actions?: ReactNode }) {
  return (
    <div className="pc-contact">
      <div className="pc-contact__body">
        <p className="pc-contact__name">
          {route.label}
          {route.is_default && <span className="pc-tag">Default</span>}
        </p>
        <p className="pc-contact__meta">{routeTypeLabel(route.route_type)}</p>
        <p className="pc-contact__meta">
          <a href={routeHref(route)} rel="noopener noreferrer">
            {route.destination}
          </a>
        </p>
        {route.description && <p className="pc-contact__meta">{route.description}</p>}
      </div>
      {actions && <div className="pc-contact__actions">{actions}</div>}
    </div>
  );
}
