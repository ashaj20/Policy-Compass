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
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { focusFirstError, validateEmail } from "../../lib/validation";

type Role = "ADMIN" | "STAFF";

interface Member {
  id: string;
  email: string;
  role: Role;
  joined_at: string;
  is_you: boolean;
}

interface Invitation {
  id: string;
  email: string;
  role: Role;
  invited_at: string;
  expires_at: string;
  invited_by: string | null;
}

const ROLE_OPTIONS = [
  { value: "STAFF", label: "Staff member" },
  { value: "ADMIN", label: "Administrator" },
];
const ROLE_LABEL: Record<Role, string> = { ADMIN: "Administrator", STAFF: "Staff member" };

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

type Confirm =
  | { kind: "remove"; member: Member }
  | { kind: "revoke"; invitation: Invitation };

export function MembersPage() {
  const { user, refresh } = useAuth();
  const membership = currentMembership(user)!;
  const orgId = membership.organisation_id;
  const base = `/organisations/${orgId}`;

  const [members, setMembers] = useState<Member[]>();
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loadError, setLoadError] = useState<ApiError>();
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string }>();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [confirm, setConfirm] = useState<Confirm>();
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string>();

  const load = useCallback(async () => {
    setLoadError(undefined);
    try {
      const data = await api<{ members: Member[]; invitations: Invitation[] }>(`${base}/members`);
      setMembers(data.members);
      setInvitations(data.invitations);
    } catch (err) {
      setLoadError(err as ApiError);
    }
  }, [base]);

  useEffect(() => {
    if (membership.role === "ADMIN") load();
  }, [load, membership.role]);

  if (membership.role !== "ADMIN") {
    return (
      <AppShell>
        <PageHeader title="Organisation members" />
        <ErrorState message="You don't have permission to manage members." />
      </AppShell>
    );
  }

  async function changeRole(member: Member, role: Role) {
    setNotice(undefined);
    try {
      await api(`${base}/members/${member.id}`, { method: "PATCH", body: JSON.stringify({ role }) });
      setNotice({ tone: "success", text: `${member.email} is now ${ROLE_LABEL[role].toLowerCase()}.` });
      if (member.is_you) await refresh();
      await load();
    } catch (err) {
      setNotice({ tone: "error", text: (err as ApiError).message });
      await load(); // put the dropdown back to the saved role
    }
  }

  async function resend(invitation: Invitation) {
    setNotice(undefined);
    try {
      await api(`${base}/invitations/${invitation.id}/resend`, { method: "POST" });
      setNotice({ tone: "success", text: `We've sent a new invitation to ${invitation.email}.` });
      await load();
    } catch (err) {
      setNotice({ tone: "error", text: (err as ApiError).message });
    }
  }

  async function onConfirm() {
    if (!confirm) return;
    setConfirmBusy(true);
    setConfirmError(undefined);
    try {
      if (confirm.kind === "remove") {
        await api(`${base}/members/${confirm.member.id}`, { method: "DELETE" });
        if (confirm.member.is_you) {
          // Removing yourself ends your access; reloading the user leaves the workspace.
          await refresh();
          return;
        }
        setNotice({ tone: "success", text: `${confirm.member.email} has been removed.` });
      } else {
        await api(`${base}/invitations/${confirm.invitation.id}`, { method: "DELETE" });
        setNotice({ tone: "success", text: `The invitation to ${confirm.invitation.email} has been cancelled.` });
      }
      setConfirm(undefined);
      await load();
    } catch (err) {
      setConfirmError((err as ApiError).message);
    } finally {
      setConfirmBusy(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        title="Organisation members"
        description="Administrators manage policies and settings. Staff members ask questions and view answers."
        actions={<Button onClick={() => setInviteOpen(true)}>Add member</Button>}
      />

      {notice && <Alert tone={notice.tone} title={notice.text} />}

      {loadError ? (
        <ErrorState message="We couldn't load your members. Please try again." errorId={loadError.errorId} onRetry={load} />
      ) : !members ? (
        <div className="pc-card">
          <Skeleton lines={4} />
        </div>
      ) : (
        <>
          <section className="pc-card" aria-labelledby="members-heading">
            <h2 id="members-heading" className="pc-card__title">
              Members ({members.length})
            </h2>
            <div className="pc-table-wrap">
              <table className="pc-table">
                <thead>
                  <tr>
                    <th scope="col">Email</th>
                    <th scope="col">Role</th>
                    <th scope="col">Joined</th>
                    <th scope="col">
                      <span className="visually-hidden">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.id}>
                      <td data-label="Email">
                        {m.email}
                        {m.is_you && <span className="pc-tag">You</span>}
                      </td>
                      <td data-label="Role">
                        <Select
                          label={`Role for ${m.email}`}
                          hideLabel
                          options={ROLE_OPTIONS}
                          value={m.role}
                          onChange={(e) => changeRole(m, e.target.value as Role)}
                          className="pc-field--compact"
                        />
                      </td>
                      <td data-label="Joined">{formatDate(m.joined_at)}</td>
                      <td className="pc-table__actions">
                        <Button
                          variant="ghost"
                          onClick={() => {
                            setConfirmError(undefined);
                            setConfirm({ kind: "remove", member: m });
                          }}
                          aria-label={`Remove ${m.email}`}
                        >
                          Remove
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="pc-card" aria-labelledby="invitations-heading">
            <h2 id="invitations-heading" className="pc-card__title">
              Pending invitations ({invitations.length})
            </h2>
            {invitations.length === 0 ? (
              <EmptyState
                title="No pending invitations"
                description="People you invite will appear here until they accept."
              />
            ) : (
              <div className="pc-table-wrap">
                <table className="pc-table">
                  <thead>
                    <tr>
                      <th scope="col">Email</th>
                      <th scope="col">Role</th>
                      <th scope="col">Expires</th>
                      <th scope="col">
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {invitations.map((inv) => {
                      const expired = new Date(inv.expires_at) < new Date();
                      return (
                        <tr key={inv.id}>
                          <td data-label="Email">{inv.email}</td>
                          <td data-label="Role">{ROLE_LABEL[inv.role]}</td>
                          <td data-label="Expires">
                            {expired ? <span className="pc-tag pc-tag--warning">Expired</span> : formatDate(inv.expires_at)}
                          </td>
                          <td className="pc-table__actions">
                            <Button variant="ghost" onClick={() => resend(inv)} aria-label={`Resend invitation to ${inv.email}`}>
                              Resend
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() => {
                                setConfirmError(undefined);
                                setConfirm({ kind: "revoke", invitation: inv });
                              }}
                              aria-label={`Cancel invitation to ${inv.email}`}
                            >
                              Cancel
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {inviteOpen && (
        <InviteDialog
          base={base}
          onClose={() => setInviteOpen(false)}
          onInvited={async (email) => {
            setInviteOpen(false);
            setNotice({ tone: "success", text: `We've sent an invitation to ${email}.` });
            await load();
          }}
        />
      )}

      {confirm?.kind === "remove" && (
        <ConfirmDialog
          title="Remove this member?"
          message={
            <p>
              <strong>{confirm.member.email}</strong>{" "}
              {confirm.member.is_you ? "(you) " : ""}will lose access to {membership.organisation_name} immediately.
            </p>
          }
          confirmLabel="Remove member"
          onConfirm={onConfirm}
          onCancel={() => setConfirm(undefined)}
          busy={confirmBusy}
          error={confirmError}
        />
      )}
      {confirm?.kind === "revoke" && (
        <ConfirmDialog
          title="Cancel this invitation?"
          message={
            <p>
              The invitation link sent to <strong>{confirm.invitation.email}</strong> will stop working.
            </p>
          }
          confirmLabel="Cancel invitation"
          onConfirm={onConfirm}
          onCancel={() => setConfirm(undefined)}
          busy={confirmBusy}
          error={confirmError}
        />
      )}
    </AppShell>
  );
}

function InviteDialog({
  base,
  onClose,
  onInvited,
}: {
  base: string;
  onClose: () => void;
  onInvited: (email: string) => void;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("STAFF");
  const [error, setError] = useState<string>();
  const [formError, setFormError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(undefined);
    const problem = validateEmail(email);
    setError(problem);
    if (problem) return focusFirstError(formRef.current);
    setBusy(true);
    try {
      const inv = await api<Invitation>(`${base}/invitations`, {
        method: "POST",
        body: JSON.stringify({ email, role }),
      });
      onInvited(inv.email);
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.fields.email) {
        setError(apiErr.fields.email);
        focusFirstError(formRef.current);
      } else {
        setFormError(apiErr.message);
      }
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Add member"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="invite-form" loading={busy}>
            Send invitation
          </Button>
        </>
      }
    >
      <p className="pc-auth__muted">We'll email them a link to join. It expires in 7 days.</p>
      {formError && <Alert tone="error" title={formError} />}
      <form id="invite-form" ref={formRef} onSubmit={onSubmit} noValidate>
        <Input
          label="Email"
          type="email"
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={error}
          data-autofocus
        />
        <Select label="Role" options={ROLE_OPTIONS} value={role} onChange={(e) => setRole(e.target.value as Role)} />
      </form>
    </Modal>
  );
}
