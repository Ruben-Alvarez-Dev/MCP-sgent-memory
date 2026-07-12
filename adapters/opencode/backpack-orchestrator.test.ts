import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { BackpackOrchestrator } from "./backpack-orchestrator"

// ─── Network isolation ───────────────────────────────────────────────────────
// This suite must NEVER make a real network request. On a developer machine
// (or CI box) something may legitimately be listening on 127.0.0.1:8890 (the
// MCP-agent-memory HTTP sidecar) or :7437 (Engram Go) — hitting either for
// real from a test run risks writing live events into a real memory store.
// Every fetch() call the plugin makes (isEngramRunning, engramFetch,
// backpackPost, backpackPostAwaited, fetchContext) goes through the global
// `fetch`, so stubbing it here covers all of them regardless of which hook
// exercises it.
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(async () => ({
    ok: false,
    status: 503,
    json: async () => null,
  })) as unknown as typeof fetchMock
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function loadHooks() {
  return BackpackOrchestrator({
    directory: process.cwd(),
    client: {} as never,
    $: {} as never,
    worktree: process.cwd(),
  } as never)
}

describe("BackpackOrchestrator plugin (smoke test)", () => {
  it("imports without throwing and exposes the expected shape", () => {
    expect(typeof BackpackOrchestrator).toBe("function")
  })

  it("instantiates without making a real network request (fetch is mocked)", async () => {
    // Every network call in the plugin is wrapped in try/catch with an
    // AbortSignal timeout, so instantiation must resolve cleanly even when
    // the mocked fetch reports both backends unreachable.
    const hooks = await loadHooks()

    expect(hooks).toBeTruthy()
    expect(typeof hooks.event).toBe("function")
    expect(typeof hooks["chat.message"]).toBe("function")
    expect(typeof hooks["tool.execute.before"]).toBe("function")
    expect(typeof hooks["tool.execute.after"]).toBe("function")
    expect(typeof hooks["experimental.chat.system.transform"]).toBe("function")
    expect(typeof hooks["experimental.session.compacting"]).toBe("function")

    // Prove the mock actually intercepted the call (isEngramRunning fires
    // during instantiation) rather than a real request silently succeeding.
    expect(fetchMock).toHaveBeenCalled()
  })

  it("blocks a non-conventional commit message via tool.execute.before", async () => {
    const hooks = await loadHooks()

    await expect(
      hooks["tool.execute.before"](
        { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
        { args: { command: 'git commit -m "not conventional"' } } as never
      )
    ).rejects.toThrow(/BLOCKED: Commit message must follow Conventional Commits format/)

    // A conventional commit message must NOT throw.
    await expect(
      hooks["tool.execute.before"](
        { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
        { args: { command: 'git commit -m "feat(adapters): recover plugin"' } } as never
      )
    ).resolves.toBeUndefined()
  })

  describe("commit message extraction regex fix", () => {
    it("allows a heredoc-style multi-line conventional commit message", async () => {
      const hooks = await loadHooks()
      const cmd = [
        `git commit -m "$(cat <<'EOF'`,
        `feat(x): summary`,
        ``,
        `longer body explaining the change`,
        `EOF`,
        `)"`,
      ].join("\n")

      await expect(
        hooks["tool.execute.before"](
          { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
          { args: { command: cmd } } as never
        )
      ).resolves.toBeUndefined()
    })

    it("blocks a heredoc-style multi-line non-conventional commit message", async () => {
      const hooks = await loadHooks()
      const cmd = [
        `git commit -m "$(cat <<'EOF'`,
        `not conventional at all`,
        ``,
        `body text`,
        `EOF`,
        `)"`,
      ].join("\n")

      await expect(
        hooks["tool.execute.before"](
          { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
          { args: { command: cmd } } as never
        )
      ).rejects.toThrow(/BLOCKED: Commit message must follow Conventional Commits format/)
    })

    it("validates the FIRST -m flag (subject), not the second (body), with two -m flags", async () => {
      const hooks = await loadHooks()

      // Conventional subject + arbitrary body must be allowed.
      await expect(
        hooks["tool.execute.before"](
          { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
          {
            args: {
              command: 'git commit -m "feat(x): summary" -m "longer body"',
            },
          } as never
        )
      ).resolves.toBeUndefined()

      // Non-conventional subject must be blocked even though the second
      // -m flag's body text is irrelevant to the check.
      await expect(
        hooks["tool.execute.before"](
          { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
          {
            args: {
              command: 'git commit -m "not conventional" -m "longer body"',
            },
          } as never
        )
      ).rejects.toThrow(/BLOCKED: Commit message must follow Conventional Commits format/)
    })

    it("handles git commit --amend with -m", async () => {
      const hooks = await loadHooks()

      await expect(
        hooks["tool.execute.before"](
          { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
          { args: { command: 'git commit --amend -m "fix(x): correct typo"' } } as never
        )
      ).resolves.toBeUndefined()

      await expect(
        hooks["tool.execute.before"](
          { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
          { args: { command: 'git commit --amend -m "bad message"' } } as never
        )
      ).rejects.toThrow(/BLOCKED: Commit message must follow Conventional Commits format/)
    })

    it("allows a breaking-change '!' marker commit message", async () => {
      const hooks = await loadHooks()

      await expect(
        hooks["tool.execute.before"](
          { tool: "bash", sessionID: "test-session", callID: "test-call" } as never,
          { args: { command: 'git commit -m "feat(x)!: breaking change"' } } as never
        )
      ).resolves.toBeUndefined()
    })
  })
})
