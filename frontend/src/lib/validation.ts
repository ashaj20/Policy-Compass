/**
 * Client-side checks that mirror the API's rules (backend/app/auth/validation.py), so people get
 * instant feedback. The API remains the authority and re-checks everything.
 */

export const PASSWORD_MIN_LENGTH = 10;
const PASSWORD_MAX_LENGTH = 128;

export function validateEmail(value: string): string | undefined {
  const v = value.trim();
  if (!v) return "Enter your email address";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) {
    return "Enter a valid email address, like name@organisation.org";
  }
}

export function validateNewPassword(password: string, email?: string): string | undefined {
  if (!password) return "Enter a password";
  if (password.length < PASSWORD_MIN_LENGTH) return `Use at least ${PASSWORD_MIN_LENGTH} characters`;
  if (password.length > PASSWORD_MAX_LENGTH) return `Use no more than ${PASSWORD_MAX_LENGTH} characters`;
  if (!password.trim()) return "Your password can't be only spaces";
  if (email && password.trim().toLowerCase() === email.trim().toLowerCase()) {
    return "Your password can't be your email address";
  }
}

export function validateConfirmation(password: string, confirmation: string): string | undefined {
  if (!confirmation) return "Confirm your password";
  if (password !== confirmation) return "The passwords don't match";
}

export type FieldErrors = Record<string, string | undefined>;

export function hasErrors(errors: FieldErrors): boolean {
  return Object.values(errors).some(Boolean);
}

/** Move keyboard focus to the first invalid field after a failed submit. */
export function focusFirstError(form: HTMLFormElement | null) {
  requestAnimationFrame(() => {
    form?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  });
}
