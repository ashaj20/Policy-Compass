import type { CSSProperties } from "react";
import { brandStyle } from "../lib/colour";

interface PublicPreviewProps {
  name: string;
  logoUrl: string | null;
  colour: string;
}

/** A small, non-interactive preview of the public page with the chosen branding (US-028). */
export function PublicPreview({ name, logoUrl, colour }: PublicPreviewProps) {
  return (
    <figure className="pc-preview" style={brandStyle(colour) as CSSProperties} aria-label="Preview of your public page">
      <div className="pc-preview__header">
        {logoUrl && <img src={logoUrl} alt="" className="pc-preview__logo" />}
        <span className="pc-preview__name">{name}</span>
      </div>
      <div className="pc-preview__body" aria-hidden="true">
        <p className="pc-preview__title">How can we help?</p>
        <div className="pc-preview__input">What would you like to know?</div>
        <span className="pc-preview__button">Ask</span>
      </div>
    </figure>
  );
}