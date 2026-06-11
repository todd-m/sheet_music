import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Tests construct their own JSDOM and load app/lib.js into it via a
    // data-URL import, so the suite runs in the node environment and
    // istanbul coverage cannot instrument lib.js — no coverage gate here.
    environment: "node",
    include: ["tests/test_client.js"],
  },
});
