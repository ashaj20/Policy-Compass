import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  Alert,
  AppShell,
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  PageHeader,
  Select,
  Skeleton,
} from "../../components";
import { ContactCard, HelpRouteCard } from "../../components/ContactCard";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import {
  ROUTE_TYPES,
  validateDestination,
  validatePhone,
  type Contacts,
  type HelpRoute,
  type PolicyOwner,
  type RouteType,
} from "../../lib/contacts";
import { focusFirstError, hasErrors, validateEmail, type FieldErrors } from "../../lib/validation";

type Editing =
  | { kind: "owner"; owner?: PolicyOwner }
  | { kind: "route"; route?: HelpRoute };
type Deleting = { kind: "owner"; owner: PolicyOwner } | { kind: "route"; route: HelpRoute };

/** Internal policy owners and public help routes (US-024). Administrators manage them. */
export function ContactsPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const base = `/organisations/${membership.organisation_id}`;

  const [data, setData] = useState<Contacts>();
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();
  const [editing, setEditing] = useState<Editing>();
  const [deleting, setDeleting] = useState<Deleting>();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string>();

  const load = useCallback(async () => {
    setError(undefined);
    try {
      setData(await api<Contacts>(`${base}/contacts`));
    } catch (err) {
      setError(err as ApiError);
    }
  }, [base]);

  useEffect(() => {
    load();
  }, [load]);

  async function onDelete() {
    if (!deleting) return;
    setBusy(true);
    setActionError(undefined);
    try {
      if (deleting.kind === "owner") {
        await api(`${base}/policy-owners/${deleting.owner.id}`, { method: "DELETE" });
        setNotice(`${deleting.owner.name} has been removed.`);
      } else {
        await api(`${base}/help-routes/${deleting.route.id}`, { method: "DELETE" });
        setNotice(`${deleting.route.label} has been removed.`);
      }
      setDeleting(undefined);
      await load();
    } catch (err) {
      setActionError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function makeDefault(route: HelpRoute) {
    try {
      await api(`${base}/help-routes/${route.id}/default`, { method: "POST" });
      setNotice(`${route.label} is now the default help route.`);
      await load();
    } catch (err) {
      setNotice(undefined);
      setActionError((err as ApiError).message);
    }
  }

  const usage = (count = 0) => (count === 0 ? "Not used by any policy" : `Used by ${count} ${count === 1 ? "policy" : "policies"}`);

  return (
    <AppShell>
      <PageHeader
        title="Contacts"
        description="Where Policy Compass directs people when it can't find enough information to answer."
      />
      {notice && <Alert tone="success" title={notice} />}
      {actionError && !deleting && <Alert tone="error" title={actionError} />}

      {error ? (
        <ErrorState message="We couldn't load your contacts. Please try again." errorId={error.errorId} onRetry={load} />
      ) : !data ? (
        <div className="pc-card">
          <Skeleton lines={6} />
        </div>
      ) : (
        <div className="pc-contacts-grid">
          <section className="pc-card pc-contacts pc-contacts--internal" aria-labelledby="owners-heading">
            <div className="pc-contacts__head">
              <div>
                <h2 id="owners-heading" className="pc-card__title">
                  <span aria-hidden="true">🔒 </span>Internal policy owners
                </h2>
                <p className="pc-contacts__scope">Staff only. Never shown to the public.</p>
              </div>
              {isAdmin && <Button onClick={() => setEditing({ kind: "owner" })}>+ Add contact</Button>}
            </div>
            {data.owners.length === 0 ? (
              <EmptyState
                title="No contacts configured"
                description="Add a policy owner so staff know where to go when Policy Compass cannot find an answer."
                action={isAdmin && <Button onClick={() => setEditing({ kind: "owner" })}>Add contact</Button>}
              />
            ) : (
              <ul className="pc-contact-list">
                {data.owners.map((o) => (
                  <li key={o.id}>
                    <ContactCard
                      owner={o}
                      actions={
                        <>
                          <span className="pc-field__hint">{usage(o.policy_count)}</span>
                          {isAdmin && (
                            <span className="pc-contact__buttons">
                              <Button variant="ghost" onClick={() => setEditing({ kind: "owner", owner: o })} aria-label={`Edit ${o.name}`}>
                                Edit
                              </Button>
                              <Button variant="ghost" onClick={() => setDeleting({ kind: "owner", owner: o })} aria-label={`Remove ${o.name}`}>
                                Remove
                              </Button>
                            </span>
                          )}
                        </>
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="pc-card pc-contacts pc-contacts--public" aria-labelledby="routes-heading">
            <div className="pc-contacts__head">
              <div>
                <h2 id="routes-heading" className="pc-card__title">
                  <span aria-hidden="true">🌐 </span>Public help routes
                </h2>
                <p className="pc-contacts__scope">Shown to the public when an answer can't be found.</p>
              </div>
              {isAdmin && <Button onClick={() => setEditing({ kind: "route" })}>+ Add route</Button>}
            </div>
            {data.help_routes.length === 0 ? (
              <EmptyState
                title="No public help route configured"
                description="Add a customer-facing route so Policy Compass can direct visitors to the right place when it cannot answer a question."
                action={isAdmin && <Button onClick={() => setEditing({ kind: "route" })}>Add help route</Button>}
              />
            ) : (
              <ul className="pc-contact-list">
                {data.help_routes.map((r) => (
                  <li key={r.id}>
                    <HelpRouteCard
                      route={r}
                      actions={
                        <>
                          <span className="pc-field__hint">
                            {r.is_default ? "Used when a policy has no route of its own" : usage(r.policy_count)}
                          </span>
                          {isAdmin && (
                            <span className="pc-contact__buttons">
                              {!r.is_default && (
                                <Button variant="ghost" onClick={() => makeDefault(r)} aria-label={`Make ${r.label} the default`}>
                                  Make default
                                </Button>
                              )}
                              <Button variant="ghost" onClick={() => setEditing({ kind: "route", route: r })} aria-label={`Edit ${r.label}`}>
                                Edit
                              </Button>
                              <Button variant="ghost" onClick={() => setDeleting({ kind: "route", route: r })} aria-label={`Remove ${r.label}`}>
                                Remove
                              </Button>
                            </span>
                          )}
                        </>
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {editing?.kind === "owner" && (
        <OwnerDialog
          base={base}
          owner={editing.owner}
          onClose={() => setEditing(undefined)}
          onSaved={async (name) => {
            setEditing(undefined);
            setNotice(editing.owner ? `${name} has been updated.` : `${name} has been added.`);
            await load();
          }}
        />
      )}
      {editing?.kind === "route" && (
        <RouteDialog
          base={base}
          route={editing.route}
          onClose={() => setEditing(undefined)}
          onSaved={async (label) => {
            setEditing(undefined);
            setNotice(editing.route ? `${label} has been updated.` : `${label} has been added.`);
            await load();
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title={deleting.kind === "owner" ? `Remove ${deleting.owner.name}?` : `Remove ${deleting.route.label}?`}
          message={
            <p>
              {(() => {
                const count = deleting.kind === "owner" ? deleting.owner.policy_count ?? 0 : deleting.route.policy_count ?? 0;
                return count > 0
                  ? `${count} ${count === 1 ? "policy uses" : "policies use"} this contact. They will show "Not assigned" until you choose another.`
                  : "No policies use this contact.";
              })()}
            </p>
          }
          confirmLabel="Remove"
          onConfirm={onDelete}
          onCancel={() => {
            setDeleting(undefined);
            setActionError(undefined);
          }}
          busy={busy}
          error={actionError}
        />
      )}
    </AppShell>
  );
}

function OwnerDialog({
  base,
  owner,
  onClose,
  onSaved,
}: {
  base: string;
  owner?: PolicyOwner;
  onClose: () => void;
  onSaved: (name: string) => void;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [name, setName] = useState(owner?.name ?? "");
  const [jobTitle, setJobTitle] = useState(owner?.job_title ?? "");
  const [email, setEmail] = useState(owner?.email ?? "");
  const [phone, setPhone] = useState(owner?.phone ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found: FieldErrors = {
      name: name.trim() ? undefined : "Enter the contact's name",
      email: email.trim() ? validateEmail(email) : undefined,
      phone: validatePhone(phone) ?? (!email.trim() && !phone.trim() ? "Enter an email address or phone number" : undefined),
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);
    setSaving(true);
    try {
      const saved = await api<PolicyOwner>(owner ? `${base}/policy-owners/${owner.id}` : `${base}/policy-owners`, {
        method: owner ? "PUT" : "POST",
        body: JSON.stringify({ name, job_title: jobTitle, email, phone }),
      });
      onSaved(saved.name);
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) setErrors(apiErr.fields);
      else setFormError(apiErr.message);
      setSaving(false);
    }
  }

  return (
    <Modal
      title={owner ? "Edit policy owner" : "Add policy owner"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="owner-form" loading={saving}>
            {owner ? "Save changes" : "Add contact"}
          </Button>
        </>
      }
    >
      <p className="pc-auth__muted">Shown to staff only. Policy owners are never shown on public pages.</p>
      {formError && <Alert tone="error" title={formError} />}
      <form id="owner-form" ref={formRef} onSubmit={onSubmit} noValidate>
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} data-autofocus />
        <Input label="Job title (optional)" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} error={errors.job_title} />
        <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} />
        <Input label="Phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} error={errors.phone} hint="Enter an email address, a phone number, or both." />
      </form>
    </Modal>
  );
}

function RouteDialog({
  base,
  route,
  onClose,
  onSaved,
}: {
  base: string;
  route?: HelpRoute;
  onClose: () => void;
  onSaved: (label: string) => void;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [label, setLabel] = useState(route?.label ?? "");
  const [type, setType] = useState<RouteType>(route?.route_type ?? "EMAIL");
  const [destination, setDestination] = useState(route?.destination ?? "");
  const [description, setDescription] = useState(route?.description ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const typeInfo = ROUTE_TYPES.find((t) => t.value === type)!;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const found: FieldErrors = {
      label: label.trim() ? undefined : "Enter a label, for example Repairs Helpdesk",
      destination: validateDestination(type, destination),
    };
    setErrors(found);
    if (hasErrors(found)) return focusFirstError(formRef.current);
    setSaving(true);
    try {
      const saved = await api<HelpRoute>(route ? `${base}/help-routes/${route.id}` : `${base}/help-routes`, {
        method: route ? "PUT" : "POST",
        body: JSON.stringify({ label, route_type: type, destination, description }),
      });
      onSaved(saved.label);
    } catch (err) {
      const apiErr = err as ApiError;
      if (Object.keys(apiErr.fields).length) setErrors(apiErr.fields);
      else setFormError(apiErr.message);
      setSaving(false);
    }
  }

  return (
    <Modal
      title={route ? "Edit public help route" : "Add public help route"}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="route-form" loading={saving}>
            {route ? "Save changes" : "Add route"}
          </Button>
        </>
      }
    >
      <p className="pc-auth__muted">Shown to members of the public when Policy Compass can't answer their question.</p>
      {formError && <Alert tone="error" title={formError} />}
      <form id="route-form" ref={formRef} onSubmit={onSubmit} noValidate>
        <Select
          label="Type"
          options={ROUTE_TYPES.map((t) => ({ value: t.value, label: t.label }))}
          value={type}
          onChange={(e) => setType(e.target.value as RouteType)}
        />
        <Input label="Label" placeholder="e.g. Repairs Helpdesk" value={label} onChange={(e) => setLabel(e.target.value)} error={errors.label} />
        <Input
          label={typeInfo.destination}
          type={type === "EMAIL" ? "email" : type === "PHONE" ? "tel" : "url"}
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          error={errors.destination}
        />
        <Input label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} error={errors.description} />
      </form>
    </Modal>
  );
}
