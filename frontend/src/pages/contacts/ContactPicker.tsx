import { Link } from "react-router-dom";
import { Select } from "../../components";

interface ContactPickerProps {
  kind: "owner" | "route";
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

const TEXT = {
  owner: {
    label: "Internal policy owner",
    hint: "Staff are directed here when an answer can't be found. Never shown to the public.",
    none: "No policy owners yet.",
    add: "Add one in Contacts",
  },
  route: {
    label: "Public help route",
    hint: "The public are directed here when an answer can't be found. If not chosen, your default route is used.",
    none: "No public help routes yet.",
    add: "Add one in Contacts",
  },
};

/** Choose a policy owner or public help route for a policy (US-024). */
export function ContactPicker({ kind, options, value, onChange, error }: ContactPickerProps) {
  const t = TEXT[kind];
  if (options.length === 0) {
    return (
      <div className="pc-upload__contact">
        <p className="pc-field__label">{t.label}</p>
        <p className="pc-field__hint">
          {t.none} <Link to="/internal/contacts">{t.add}</Link>.
        </p>
      </div>
    );
  }
  return (
    <div className="pc-upload__contact">
      <Select
        label={t.label}
        options={[{ value: "", label: "Not assigned" }, ...options]}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        error={error}
      />
      <p className="pc-field__hint">{t.hint}</p>
    </div>
  );
}