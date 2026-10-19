import { afterEach, describe, expect, it } from "vitest";
// The real file websites load, as text.
import WIDGET from "../public/widget.js?raw";

function load(attrs: Record<string, string>) {
  const script = document.createElement("script");
  script.src = "https://compass.example/widget.js";
  for (const [k, v] of Object.entries(attrs)) script.setAttribute(k, v);
  Object.defineProperty(document, "currentScript", { value: script, configurable: true });
  new Function(WIDGET)();
}

afterEach(() => {
  document.body.innerHTML = "";
  document.head.innerHTML = "";
  delete (window as unknown as Record<string, unknown>).__policyCompassWidget;
});

describe("Website widget script (US-030)", () => {
  it("adds a labelled button that opens the public page in a panel, loaded only on first open", () => {
    load({ "data-organisation": "riverside-housing" });
    const button = document.querySelector<HTMLButtonElement>(".pcw-button")!;
    const panel = document.getElementById("pcw-panel")!;
    expect(button.textContent).toBe("Ask a question");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(panel.hidden).toBe(true);
    expect(document.querySelector("iframe")).toBeNull();

    button.click();
    const frame = document.querySelector("iframe")!;
    expect(frame.src).toBe("https://compass.example/p/riverside-housing/widget");
    expect(frame.title).toBe("Ask a question");
    expect(panel.hidden).toBe(false);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(panel.getAttribute("role")).toBe("dialog");

    document.querySelector<HTMLButtonElement>(".pcw-close")!.click();
    expect(panel.hidden).toBe(true);
    expect(document.activeElement).toBe(button);

    button.click();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(panel.hidden).toBe(true);
    expect(document.querySelectorAll("iframe")).toHaveLength(1);
  });

  it("uses the label, colour and side given, as plain text", () => {
    load({
      "data-organisation": "riverside-housing",
      "data-label": "<img src=x onerror=alert(1)>Help",
      "data-colour": "#ffd700",
      "data-position": "left",
    });
    const button = document.querySelector<HTMLButtonElement>(".pcw-button")!;
    expect(button.textContent).toBe("<img src=x onerror=alert(1)>Help");
    expect(button.querySelector("img")).toBeNull();
    const css = document.querySelector("style")!.textContent!;
    expect(css).toContain("background:#ffd700");
    expect(css).toContain("color:#141b24"); // dark text on a light colour
    expect(css).toContain("left:20px");
  });

  it("ignores unsafe or missing settings", () => {
    load({ "data-organisation": "../../internal", "data-colour": "red;}body{display:none" });
    expect(document.querySelector(".pcw-button")).toBeNull();

    delete (window as unknown as Record<string, unknown>).__policyCompassWidget;
    load({ "data-organisation": "riverside-housing", "data-colour": "red;}body{display:none" });
    expect(document.querySelector("style")!.textContent).toContain("background:#1f5aa6");
  });

  it("only adds one widget even if the code is pasted twice", () => {
    load({ "data-organisation": "riverside-housing" });
    load({ "data-organisation": "riverside-housing" });
    expect(document.querySelectorAll(".pcw-button")).toHaveLength(1);
  });
});
