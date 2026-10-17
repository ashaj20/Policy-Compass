import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell, Button, EmptyState, ErrorState, Input, PageHeader, Select, Skeleton } from "../../components";
import { AudienceBadge } from "../../components/AudienceBadge";
import { StatusBadge } from "../../components/StatusBadge";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";
import { formatLongDate } from "../../lib/format";
import { STATUS_LABELS, type Audience, type VersionStatus } from "../../lib/policy";

interface PolicyListItem {
  id: string;
  name: string;
  category: string;
  audience: Audience;
  status: VersionStatus;
  version: string;
  effective_date: string;
  updated_at: string;
  owner: string | null;
}

interface PolicyList {
  policies: PolicyListItem[];
  categories: string[];
}

const FILTER_KEYS = ["q", "audience", "status", "category"] as const;

const AUDIENCE_FILTER = [
  { value: "", label: "All audiences" },
  { value: "INTERNAL", label: "Internal" },
  { value: "PUBLIC", label: "Public" },
  { value: "BOTH", label: "Both" },
];

const STATUS_FILTER = [
  { value: "", label: "All statuses" },
  ...(["READY", "PROCESSING", "FAILED", "DRAFT", "ARCHIVED", "SUPERSEDED"] as VersionStatus[]).map((s) => ({
    value: s,
    label: STATUS_LABELS[s],
  })),
];

/** The organisation's policies (US-022). Administrators manage; staff see ready policies only. */
export function PoliciesPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [data, setData] = useState<PolicyList>();
  const [error, setError] = useState<ApiError>();

  const query = FILTER_KEYS.filter((k) => params.get(k))
    .map((k) => `${k}=${encodeURIComponent(params.get(k)!)}`)
    .join("&");
  const filtered = query.length > 0;

  const load = useCallback(async () => {
    setError(undefined);
    try {
      setData(await api<PolicyList>(`/organisations/${membership.organisation_id}/policies${query ? `?${query}` : ""}`));
    } catch (err) {
      setError(err as ApiError);
    }
  }, [membership.organisation_id, query]);

  useEffect(() => {
    load();
  }, [load]);

  // Apply the search shortly after typing stops.
  useEffect(() => {
    const timer = setTimeout(() => {
      if ((params.get("q") ?? "") !== search.trim()) setFilter("q", search.trim());
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  function clearFilters() {
    setSearch("");
    setParams(new URLSearchParams(), { replace: true });
  }

  const categoryOptions = [{ value: "", label: "All categories" }, ...(data?.categories ?? []).map((c) => ({ value: c, label: c }))];

  return (
    <AppShell>
      <PageHeader
        title="Policies"
        description={
          isAdmin
            ? "Your organisation's approved policies and their processing status."
            : "Approved policies that Policy Compass uses to answer questions."
        }
        actions={
          isAdmin && (
            <Link to="/internal/policies/new" className="pc-button pc-button--primary">
              + Upload policy
            </Link>
          )
        }
      />

      <section className="pc-card" aria-label="Policy list">
        <div className="pc-filters" role="search">
          <Input
            label="Search policies"
            type="search"
            placeholder="Search by name or category"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pc-filters__search"
          />
          <Select
            label="Audience"
            options={AUDIENCE_FILTER}
            value={params.get("audience") ?? ""}
            onChange={(e) => setFilter("audience", e.target.value)}
          />
          {isAdmin && (
            <Select
              label="Status"
              options={STATUS_FILTER}
              value={params.get("status") ?? ""}
              onChange={(e) => setFilter("status", e.target.value)}
            />
          )}
          <Select
            label="Category"
            options={categoryOptions}
            value={params.get("category") ?? ""}
            onChange={(e) => setFilter("category", e.target.value)}
          />
        </div>

        {error ? (
          <ErrorState message="We couldn't load your policies. Please try again." errorId={error.errorId} onRetry={load} />
        ) : !data ? (
          <Skeleton lines={6} />
        ) : data.policies.length === 0 ? (
          filtered ? (
            <EmptyState
              title="No policies match these filters"
              description="Try a different search or clear the filters."
              action={
                <Button variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : isAdmin ? (
            <EmptyState
              title="No policies yet"
              description="Upload your first approved policy to start building your knowledge base."
              action={
                <Link to="/internal/policies/new" className="pc-button pc-button--primary">
                  Upload policy
                </Link>
              }
            />
          ) : (
            <EmptyState
              title="No policies available yet"
              description="Policies appear here once your administrators have added and approved them."
            />
          )
        ) : (
          <>
            <p className="pc-field__hint" role="status">
              {data.policies.length} {data.policies.length === 1 ? "policy" : "policies"}
              {filtered ? " match your filters" : ""}
            </p>
            <div className="pc-table-wrap">
              <table className="pc-table">
                <thead>
                  <tr>
                    <th scope="col">Policy</th>
                    <th scope="col">Audience</th>
                    <th scope="col">Version</th>
                    <th scope="col">Status</th>
                    <th scope="col">Effective date</th>
                    <th scope="col">Owner</th>
                  </tr>
                </thead>
                <tbody>
                  {data.policies.map((p) => (
                    <tr key={p.id}>
                      <td data-label="Policy">
                        <span className="pc-table__primary">{p.name}</span>
                        <span className="pc-table__secondary">{p.category}</span>
                      </td>
                      <td data-label="Audience">
                        <AudienceBadge audience={p.audience} />
                      </td>
                      <td data-label="Version">{p.version}</td>
                      <td data-label="Status">
                        <StatusBadge status={p.status} />
                      </td>
                      <td data-label="Effective date">{formatLongDate(p.effective_date)}</td>
                      <td data-label="Owner">{p.owner ?? <span className="pc-auth__muted">Not assigned</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </AppShell>
  );
}
