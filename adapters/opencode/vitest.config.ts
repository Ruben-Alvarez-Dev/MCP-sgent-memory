import { defineConfig } from "vitest/config"

// This plugin targets OpenCode's Bun runtime, where the global `Bun` object
// is always present. Vitest's test workers run under Node, so we set
// ENGRAM_BIN explicitly — a configuration override the plugin itself already
// supports (`process.env.ENGRAM_BIN ?? Bun.which("engram") ?? ...`). This
// short-circuits the one Bun-only call that happens at module load time
// without touching or stubbing any plugin behavior.
export default defineConfig({
  test: {
    env: {
      ENGRAM_BIN: "/usr/bin/true",
    },
  },
})
