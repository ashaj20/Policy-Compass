import { useCallback, useEffect, useState } from "react";
import { Alert, AppShell, ErrorState, PageHeader, Skeleton } from "../../components";
import { api, ApiError } from "../../lib/api";

interface Rule {
  data: string;
  period: string;
  detail: string;
}

/** What Policy Compass keeps and for how long (US-035B, Spec §22). Read-only. */
export function RetentionPage() {
  const [rules, setRules] = useState<Rule[]>();
  const [error, setError] = useState<ApiError>();

  const load = useCallback(async () => {
    setError(undefined);
    try {
      setRules(await api<Rule[]>("/retention"));
    } catch (err) {
      setError(err as ApiError);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppShell>
      <PageHeader
        title="Data and retention"
        description="What Policy Compass keeps, for how long, and why. Data is removed automatically when its period ends."
      />
      <Alert tone="info" title="Please don't include personal information in questions.">
        <p>
          Questions are about policies, so names, addresses, health details or account numbers aren't needed to get an
          answer.
        </p>
      </Alert>
      <section className="pc-card" aria-labelledby="retention-heading">
        <h2 id="retention-heading" className="pc-card__title">
          Retention periods
        </h2>
        {error ? (
          <ErrorState message="We couldn't load the retention rules. Please try again." errorId={error.errorId} onRetry={load} />
        ) : !rules ? (
          <Skeleton lines={6} />
        ) : (
          <div className="pc-table-wrap">
            <table className="pc-table">
              <thead>
                <tr>
                  <th scope="col">Information</th>
                  <th scope="col">Kept for</th>
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.data}>
                    <td data-label="Information">
                      <span className="pc-table__primary">{r.data}</span>
                    </td>
                    <td data-label="Kept for">{r.period}</td>
                    <td data-label="Details">{r.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppShell>
  );
}
