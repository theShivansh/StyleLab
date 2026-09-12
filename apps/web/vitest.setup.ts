import "@testing-library/jest-dom/vitest";

// jsdom does not implement matchMedia, and src/lib/a11y.ts depends on it.
// Default to "no reduced motion" so components render their normal path in tests.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
