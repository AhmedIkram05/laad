import "@testing-library/jest-dom";

const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (key) => store[key] ?? null,
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    clear: () => { store = {}; },
    get length() { return Object.keys(store).length; },
    key: (index) => Object.keys(store)[index] ?? null,
  };
})();

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  writable: true,
  configurable: true,
});

if (typeof Element.prototype.scrollIntoView === "undefined") {
  Element.prototype.scrollIntoView = () => {};
}
