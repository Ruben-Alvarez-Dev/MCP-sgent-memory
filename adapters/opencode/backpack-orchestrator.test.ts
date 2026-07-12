import { describe, expect, it } from "vitest"
import { BackpackOrchestrator } from "./backpack-orchestrator"

describe("BackpackOrchestrator plugin (smoke test)", () => {
  it("imports without throwing and exposes the expected shape", () => {
    expect(typeof BackpackOrchestrator).toBe("function")
  })

  it("instantiates against a real directory without crashing", async () => {
    // No MCP-agent-memory sidecar (:8890) or Engram Go (:7437) is expected to be
    // running in the test environment — every network call in the plugin is
    // wrapped in try/catch with an AbortSignal timeout, so instantiation must
    // resolve cleanly even when both backends are unreachable.
    const hooks = await BackpackOrchestrator({
      directory: process.cwd(),
      client: {} as never,
      $: {} as never,
      worktree: process.cwd(),
    } as never)

    expect(hooks).toBeTruthy()
    expect(typeof hooks.event).toBe("function")
    expect(typeof hooks["chat.message"]).toBe("function")
    expect(typeof hooks["tool.execute.before"]).toBe("function")
    expect(typeof hooks["tool.execute.after"]).toBe("function")
    expect(typeof hooks["experimental.chat.system.transform"]).toBe("function")
    expect(typeof hooks["experimental.session.compacting"]).toBe("function")
  })

  it("blocks a non-conventional commit message via tool.execute.before", async () => {
    const hooks = await BackpackOrchestrator({
      directory: process.cwd(),
      client: {} as never,
      $: {} as never,
      worktree: process.cwd(),
    } as never)

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
})
