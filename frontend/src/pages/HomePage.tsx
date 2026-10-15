import { useEffect, useState } from "react";
import { Alert, LoadingState } from "../components";
import { api, ApiError } from "../lib/api";

/** Temporary landing page until US-001 adds authentication. Confirms the API is reachable. */
export function HomePage() {
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [error, setError] = useState<string>();

  useEffect(() => {
    api<{ status: string }>("/health")
      .then(() => setStatus("ok"))
      .catch((e: ApiError) => {
        setError(e.message);
        setStatus("error");
      });
  }, []);

  return (
    <main className="pc-page-centered">
      <h1>Policy Compass</h1>
      <p>Turn policies into clear answers.</p>
      {status === "loading" && <LoadingState label="Checking connection…" />}
      {status === "ok" && <Alert tone="success" title="Connected to the Policy Compass API." />}
      {status === "error" && <Alert tone="error" title={error} />}
    </main>
  );
}
