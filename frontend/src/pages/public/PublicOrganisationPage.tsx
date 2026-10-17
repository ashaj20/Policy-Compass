import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ErrorState, LoadingState } from "../../components";
import { api, ApiError } from "../../lib/api";

interface PublicOrganisation {
  name: string;
  slug: string;
  website: string | null;
  logo_url: string | null;
}

/**
 * Public page at /p/<slug>. US-002 only proves the public URL resolves to the organisation;
 * asking questions arrives with US-026/027. No internal navigation or data is shown here.
 */
export function PublicOrganisationPage() {
  const { slug = "" } = useParams();
  const [org, setOrg] = useState<PublicOrganisation>();
  const [error, setError] = useState<ApiError>();

  useEffect(() => {
    setOrg(undefined);
    setError(undefined);
    api<PublicOrganisation>(`/public/organisations/${encodeURIComponent(slug)}`)
      .then(setOrg)
      .catch(setError);
  }, [slug]);

  if (error) {
    return (
      <main className="pc-public">
        <ErrorState message={error.status === 404 ? error.message : "We couldn't load this page. Please try again."} />
      </main>
    );
  }
  if (!org) return <LoadingState label="Loading…" />;

  return (
    <div className="pc-public">
      <header className="pc-public__header">
        {org.logo_url && <img src={org.logo_url} alt="" className="pc-public__logo" />}
        <span className="pc-public__name">{org.name}</span>
      </header>
      <main className="pc-public__main">
        <h1>How can we help?</h1>
        <p className="pc-auth__muted">
          {org.name}'s policy questions page is being set up. Please check back soon.
        </p>
        {org.website && (
          <p>
            <a href={org.website} rel="noopener noreferrer">
              Visit {org.name}'s website
            </a>
          </p>
        )}
      </main>
    </div>
  );
}
