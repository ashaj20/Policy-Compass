import { useState } from "react";
import { Alert, Button } from "../../components";
import { api, ApiError } from "../../lib/api";

/** "Send a new link" button used after signup, on expired links and on unverified sign-in. */
export function ResendVerification({ email, label = "Send a new link" }: { email: string; label?: string }) {
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string>();

  async function resend() {
    setState("sending");
    setError(undefined);
    try {
      await api("/auth/resend-verification", { method: "POST", body: JSON.stringify({ email }) });
      setState("sent");
    } catch (err) {
      setError((err as ApiError).message);
      setState("idle");
    }
  }

  if (state === "sent") {
    return <Alert tone="success" title="We've sent a new verification link. Check your inbox." />;
  }
  return (
    <>
      {error && <Alert tone="error" title={error} />}
      <Button variant="secondary" onClick={resend} loading={state === "sending"}>
        {label}
      </Button>
    </>
  );
}
