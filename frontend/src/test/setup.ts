import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Wait up to 3s for elements to appear (default 1s), so slow machines don't cause false failures.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => cleanup());