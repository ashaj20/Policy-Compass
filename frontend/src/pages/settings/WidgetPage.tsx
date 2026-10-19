import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, AppShell, ErrorState, PageHeader, Skeleton } from "../../components";
import { api, ApiError } from "../../lib/api";
import { currentMembership, useAuth } from "../../lib/auth";

interface PublicInfo {
  name: string;
  slug: string;
  primary_colour: string;
  accepting_questions: boolean;
}

/** A read-only code box with a copy button. */
function CodeBlock({ label, code }: { label: string; code: string }) {
  const id = useId();
  const [copied, setCopied] = useState<boolean>();
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="pc-code">
      <label htmlFor={id} className="pc-field__label">
        {label}
      </label>
      <textarea id={id} className="pc-input pc-code__text" readOnly value={code} rows={code.split("\n").length + 1} onFocus={(e) => e.target.select()} />
      <div className="pc-code__actions">
        <button type="button" className="pc-button pc-button--secondary" onClick={copy}>
          Copy code
        </button>
        <span role="status" className="pc-field__hint">
          {copied === true ? "Copied." : copied === false ? "Couldn't copy. Select the code and copy it yourself." : ""}
        </span>
      </div>
    </div>
  );
}

/** How to put Policy Compass on the organisation's website (US-030). Administrators only. */
export function WidgetPage() {
  const { user } = useAuth();
  const membership = currentMembership(user)!;
  const isAdmin = membership.role === "ADMIN";
  const [info, setInfo] = useState<PublicInfo>();
  const [error, setError] = useState<ApiError>();

  useEffect(() => {
    if (!isAdmin) return;
    api<PublicInfo>(`/public/organisations/${encodeURIComponent(membership.organisation_slug)}`)
      .then(setInfo)
      .catch(setError);
  }, [isAdmin, membership.organisation_slug]);

  if (!isAdmin) {
    return (
      <AppShell>
        <PageHeader title="Website widget" />
        <ErrorState message="You don't have permission to manage the website widget." />
      </AppShell>
    );
  }

  const origin = window.location.origin;
  const slug = membership.organisation_slug;
  const script = info
    ? `<script src="${origin}/widget.js" data-organisation="${slug}" data-colour="${info.primary_colour}" async></script>`
    : "";
  const iframe = `<iframe src="${origin}/p/${slug}/widget" title="Ask a question" width="100%" height="640" style="border:0"></iframe>`;

  return (
    <AppShell>
      <PageHeader
        title="Website widget"
        description="Let visitors to your website ask questions about your public policies without leaving your site."
      />
      {error ? (
        <ErrorState message="We couldn't load your widget settings. Please try again." errorId={error.errorId} />
      ) : !info ? (
        <div className="pc-card">
          <Skeleton lines={4} />
        </div>
      ) : (
        <>
          {!info.accepting_questions && (
            <Alert tone="warning" title="Your public page isn't answering questions yet.">
              <p>
                Approve at least one policy with the audience Public or Both, and the widget will start answering. Until then it
                shows that the page is being set up.
              </p>
            </Alert>
          )}
          <section className="pc-card" aria-labelledby="widget-button-heading">
            <h2 id="widget-button-heading" className="pc-card__title">
              Add a question button
            </h2>
            <p>
              Paste this into your website's pages, just before <code>&lt;/body&gt;</code>. It adds an “Ask a question” button in
              the corner that opens your public Policy Compass page in a panel.
            </p>
            <CodeBlock label="Widget code" code={script} />
            <p className="pc-field__hint">
              Optional: add <code>data-label="Your text"</code> to change the button text, or <code>data-position="left"</code>{" "}
              to move it to the left.
            </p>
            <p>
              <a href={`/widget-demo.html?org=${encodeURIComponent(slug)}&colour=${encodeURIComponent(info.primary_colour)}`} target="_blank" rel="noopener">
                Preview the button on a sample web page
              </a>
            </p>
          </section>

          <section className="pc-card" aria-labelledby="widget-embed-heading">
            <h2 id="widget-embed-heading" className="pc-card__title">
              Or embed it in a page
            </h2>
            <p>If you'd rather show Policy Compass inside one of your pages, such as a help page, use this instead.</p>
            <CodeBlock label="Embed code" code={iframe} />
            <p>
              <a href={`/p/${slug}/widget`} target="_blank" rel="noopener">
                Preview the embedded page
              </a>
            </p>
          </section>

          <section className="pc-card" aria-labelledby="widget-safety-heading">
            <h2 id="widget-safety-heading" className="pc-card__title">
              What visitors can see
            </h2>
            <ul>
              <li>Answers only from policies with the audience Public or Both.</li>
              <li>Your public help routes when there isn't enough information, never your policy owners.</li>
              <li>Your logo and brand colour from <Link to="/internal/settings/branding">Branding</Link>.</li>
            </ul>
            <p className="pc-field__hint">
              If you change your public web address in <Link to="/internal/settings">Organisation settings</Link>, update the code on
              your website.
            </p>
          </section>
        </>
      )}
    </AppShell>
  );
}
