/**
 * backpack-orchestrator — The Definitive Enforcement Layer
 *
 * Automates all memory operations that don't need LLM judgment.
 * The agent doesn't need to remember to call heartbeat, ingest, or save —
 * this plugin does it automatically via OpenCode hooks.
 *
 * Architecture:
 *   OpenCode hooks → fetch() → http://127.0.0.1:8890/api/* → MCP-agent-memory
 *
 * What this replaces:
 *   - engram.ts's chat.message auto-capture → now goes to MCP ingest-event
 *   - engram.ts's tool.execute.after counting → now goes to MCP ingest-event
 *   - engram.ts's MEMORY_INSTRUCTIONS → replaced by compact BACKPACK_RULES
 *   - Manual "call automem_heartbeat every turn" → automatic via chat.message
 *
 * What this keeps from engram.ts:
 *   - Engram Go binary lifecycle (mem_save, mem_search, etc.)
 *   - Session registration in Engram Go
 *   - Compaction context injection from Engram Go
 */

import type { Plugin } from "@opencode-ai/plugin"

// ─── Configuration ───────────────────────────────────────────────────────────

const BACKPACK_API_URL = process.env.AUTOMEM_API_URL ?? "http://127.0.0.1:8890"
const ENGRAM_PORT = parseInt(process.env.ENGRAM_PORT ?? "7437")
const ENGRAM_URL = `http://127.0.0.1:${ENGRAM_PORT}`
const ENGRAM_BIN = process.env.ENGRAM_BIN ?? Bun.which("engram") ?? "/opt/homebrew/bin/engram"

// Memory infrastructure tools — skip these in tool.execute.after to avoid loops
const MEMORY_TOOL_PREFIXES = new Set([
  "automem_", "autodream_", "engram_", "vk_cache_",
  "conversation_store_", "mem0_", "sequential_thinking_",
])
const ENGRAM_GO_TOOLS = new Set([
  "mem_search", "mem_save", "mem_update", "mem_delete",
  "mem_suggest_topic_key", "mem_save_prompt", "mem_session_summary",
  "mem_context", "mem_stats", "mem_timeline", "mem_get_observation",
  "mem_session_start", "mem_session_end",
])

// ─── HTTP Client Helpers ─────────────────────────────────────────────────────

/**
 * Fire-and-forget POST to the Backpack API.
 * Never throws. Silently fails if server not running.
 * Used for non-critical auto-triggers (ingest events, heartbeats).
 */
async function backpackPost(path: string, body: Record<string, unknown>): Promise<void> {
  try {
    await fetch(`${BACKPACK_API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(2000),
    })
  } catch {
    // Silent fail — server not running, not a problem
  }
}

/**
 * Awaited POST to the Backpack API. Returns parsed JSON or null on failure.
 * Used for critical operations (compaction, conversation save).
 */
async function backpackPostAwaited(path: string, body: Record<string, unknown>): Promise<any> {
  try {
    const res = await fetch(`${BACKPACK_API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    })
    return await res.json()
  } catch {
    return null
  }
}

/**
 * Engram Go HTTP client (same as original engram.ts).
 */
async function engramFetch(path: string, opts: { method?: string; body?: any } = {}): Promise<any> {
  try {
    const res = await fetch(`${ENGRAM_URL}${path}`, {
      method: opts.method ?? "GET",
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: AbortSignal.timeout(3000),
    })
    return await res.json()
  } catch {
    return null
  }
}

async function isEngramRunning(): Promise<boolean> {
  try {
    const res = await fetch(`${ENGRAM_URL}/health`, { signal: AbortSignal.timeout(500) })
    return res.ok
  } catch {
    return false
  }
}

// ─── Utility Helpers ─────────────────────────────────────────────────────────

function truncate(str: string, max: number): string {
  return str && str.length > max ? str.slice(0, max) + "..." : (str ?? "")
}

function stripPrivateTags(str: string): string {
  return str ? str.replace(/<private>[\s\S]*?<\/private>/gi, "[REDACTED]").trim() : ""
}

function extractProjectName(directory: string): string {
  try {
    const result = Bun.spawnSync(["git", "-C", directory, "remote", "get-url", "origin"])
    if (result.exitCode === 0) {
      const url = result.stdout?.toString().trim()
      if (url) {
        const name = url.replace(/\.git$/, "").split(/[/:]/).pop()
        if (name) return name
      }
    }
  } catch {}
  try {
    const result = Bun.spawnSync(["git", "-C", directory, "rev-parse", "--show-toplevel"])
    if (result.exitCode === 0) {
      const root = result.stdout?.toString().trim()
      if (root) return root.split("/").pop() ?? "unknown"
    }
  } catch {}
  return directory.split("/").pop() ?? "unknown"
}

function isMemoryTool(toolName: string): boolean {
  const lower = toolName.toLowerCase()
  if (ENGRAM_GO_TOOLS.has(lower)) return true
  for (const prefix of MEMORY_TOOL_PREFIXES) {
    if (lower.startsWith(prefix)) return true
  }
  return false
}

// ─── Context Injection State ──────────────────────────────────────────────────
// Shared between chat.message (fetches context) and system.transform (injects it).
// This is the ONLY state shared between hooks — everything else is stateless.

let lastContextInjection: string = ""
let lastContextFetchTime: number = 0
const CONTEXT_FETCH_COOLDOWN_MS = 30_000 // 30 seconds between context fetches

/**
 * Fetch context from vk-cache for the user's query.
 * Returns injection_text or empty string on failure.
 */
async function fetchContext(query: string): Promise<string> {
  const now = Date.now()
  if (now - lastContextFetchTime < CONTEXT_FETCH_COOLDOWN_MS) {
    return lastContextInjection
  }
  try {
    const res = await fetch(`${BACKPACK_API_URL}/api/request-context`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: truncate(query, 500),
        agent_id: "default",
        intent: "answer",
        token_budget: 2000,
      }),
      signal: AbortSignal.timeout(3000),
    })
    const data = await res.json()
    const text = data?.injection_text ?? ""
    lastContextInjection = text && text !== "[No relevant context found]" ? text : ""
    lastContextFetchTime = now
    return lastContextInjection
  } catch {
    return lastContextInjection
  }
}

// ─── BACKPACK RULES — Compact System Prompt Injection ─────────────────────────
// Replaces the old 120-line MEMORY_INSTRUCTIONS with 40 lines.
// Only includes instructions that NEED LLM judgment.
// Everything else is automated by the hooks above.

const BACKPACK_RULES = `## Backpack Memory — Active Protocol

### Automatic (happens without your action — the plugin handles it)
- Events are auto-captured on every tool call and user prompt
- Heartbeats track turns automatically
- Conversations are saved on compaction
- Memory consolidation runs on thresholds

### You MUST do (requires your judgment)

When making architecture/design decisions:
→ Call automem_memorize with type="decision"

When fixing a non-obvious bug:
→ Call automem_memorize with type="bugfix"

When discovering something surprising about the codebase:
→ Call automem_memorize with type="discovery"

When the user asks to recall past work ("remember", "recall", "acordate", "qué hicimos"):
→ Call vk_cache_request_context first, then automem_memorize if needed

Before ending a session or saying "done"/"listo":
→ Call conversation_store_save_conversation with a session summary

### Anti-Rationalization Table

| Rationalization | Reality |
|---|---|
| "I'll save this memory later" | You won't. Save it NOW or it's lost. |
| "The user didn't ask me to save this" | If it's a decision, bugfix, or discovery — save it anyway. |
| "This is too simple to memorize" | Simple things become complicated. Document the expected behavior. |
| "I'll summarize at the end" | Compaction can happen at any time. Save incrementally. |
| "The plugin handles all memory" | The plugin captures EVENTS. You capture DECISIONS and DISCOVERIES. |`

// ─── Plugin Export ────────────────────────────────────────────────────────────

export const BackpackOrchestrator: Plugin = async (ctx) => {
  const project = extractProjectName(ctx.directory)

  // Track sub-agent sessions to avoid double-counting
  const subAgentSessions = new Set<string>()
  const knownSessions = new Set<string>()

  // Ensure Engram Go server is running (same as original engram.ts)
  const running = await isEngramRunning()
  if (!running) {
    try {
      Bun.spawn([ENGRAM_BIN, "serve"], {
        stdout: "ignore", stderr: "ignore", stdin: "ignore",
      })
      await new Promise((r) => setTimeout(r, 500))
    } catch {}
  }

  // Auto-import .engram/manifest.json chunks (same as original engram.ts)
  try {
    const manifestFile = `${ctx.directory}/.engram/manifest.json`
    const file = Bun.file(manifestFile)
    if (await file.exists()) {
      Bun.spawn([ENGRAM_BIN, "sync", "--import"], {
        cwd: ctx.directory,
        stdout: "ignore", stderr: "ignore", stdin: "ignore",
      })
    }
  } catch {}

  /**
   * Ensure a session exists in Engram Go. Idempotent.
   */
  async function ensureSession(sessionId: string): Promise<void> {
    if (!sessionId || knownSessions.has(sessionId)) return
    if (subAgentSessions.has(sessionId)) return
    knownSessions.add(sessionId)
    await engramFetch("/sessions", {
      method: "POST",
      body: { id: sessionId, project, directory: ctx.directory },
    })
  }

  return {
    // ─── Hook 1: Event Listener ──────────────────────────────────
    // Handles session lifecycle and file edit events.

    event: async ({ event }) => {
      // Session created — register in Engram Go
      if (event.type === "session.created") {
        const info = (event.properties as any)?.info
        const sessionId = info?.id
        const parentID = info?.parentID
        const title: string = info?.title ?? ""
        const isSubAgent = !!parentID || title.endsWith(" subagent)")

        if (sessionId && !isSubAgent) {
          await ensureSession(sessionId)
        } else if (sessionId && isSubAgent) {
          subAgentSessions.add(sessionId)
        }
      }

      // Session deleted — cleanup
      if (event.type === "session.deleted") {
        const info = (event.properties as any)?.info
        const sessionId = info?.id
        if (sessionId) {
          knownSessions.delete(sessionId)
          subAgentSessions.delete(sessionId)
        }
      }

      // Session idle — trigger dream heartbeat to check consolidation thresholds
      if (event.type === "session.idle") {
        const sessionId = (event.properties as any)?.sessionID
        if (sessionId && !subAgentSessions.has(sessionId)) {
          backpackPost("/api/heartbeat-dream", {
            agent_id: "default",
            turn_count: 1,
          })
        }
      }

      // File edited — auto-ingest
      if (event.type === "file.edited") {
        const filePath = (event.properties as any)?.file
        if (filePath) {
          backpackPost("/api/ingest-event", {
            event_type: "file_edited",
            source: "plugin",
            content: `File edited: ${filePath}`,
          })
        }
      }
    },

    // ─── Hook 2: User Prompt Capture ─────────────────────────────
    // Auto-ingest user prompt + heartbeat tick on every user message.

    "chat.message": async (input, output) => {
      if (subAgentSessions.has(input.sessionID)) return

      const content = output.parts
        .filter((p) => p.type === "text")
        .map((p) => (p as any).text ?? "")
        .join("\n")
        .trim()

      if (content.length > 10) {
        // Ensure session exists in Engram Go
        await ensureSession(input.sessionID)

        // Fire-and-forget: ingest user prompt as raw event
        backpackPost("/api/ingest-event", {
          event_type: "user_prompt",
          source: "plugin",
          content: stripPrivateTags(truncate(content, 2000)),
          session_id: input.sessionID,
        })

        // Fire-and-forget: heartbeat tick
        backpackPost("/api/heartbeat", {
          agent_id: "default",
          session_id: input.sessionID,
          turn_count: 1,
        })

        // Also capture in Engram Go (same as original engram.ts)
        engramFetch("/prompts", {
          method: "POST",
          body: {
            session_id: input.sessionID,
            content: stripPrivateTags(truncate(content, 2000)),
            project,
          },
        })

        // v1.3: Fetch relevant context for the user's query
        // Stored in lastContextInjection — injected by system.transform
        fetchContext(content)
      }
    },

    // ─── Hook 3: Tool Execute Before — Enforcement Gate ──────────
    // Blocks commit messages that don't follow Conventional Commits.

    "tool.execute.before": async (input, output) => {
      if (input.tool === "bash") {
        const cmd: string = output.args?.command ?? ""
        // Match git commit -m "message" or git commit --message="message"
        const commitMatch = cmd.match(
          /git\s+commit\s+(?:.*?\s+)?(?:-m\s+|--message[=\s]+)["']?(.+?)["']?\s*$/
        )
        if (commitMatch) {
          const msg = commitMatch[1].trim()
          const conventionalRegex =
            /^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([a-z0-9._-]+\))?!?: .+/
          if (!conventionalRegex.test(msg)) {
            throw new Error(
              `BLOCKED: Commit message must follow Conventional Commits format.\n` +
              `Got: "${msg}"\n` +
              `Expected: type(scope)?: description\n` +
              `Types: build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test\n` +
              `Example: feat(auth): add login endpoint`
            )
          }
        }
      }
    },

    // ─── Hook 4: Tool Execute After — Event Capture ──────────────
    // Auto-ingest every tool call as a raw event.

    "tool.execute.after": async (input, output) => {
      // Skip memory infrastructure tools (avoid loops)
      if (isMemoryTool(input.tool)) return

      const resultText = typeof output.output === "string"
        ? output.output.slice(0, 500)
        : JSON.stringify(output.output ?? "").slice(0, 500)

      // Fire-and-forget: ingest tool event
      backpackPost("/api/ingest-event", {
        event_type: "tool_call",
        source: "plugin",
        content: `${input.tool}: ${resultText}`,
        session_id: input.sessionID,
      })
    },

    // ─── Hook 5: System Prompt Injection ─────────────────────────
    // Inject compact BACKPACK_RULES (replaces old MEMORY_INSTRUCTIONS).

    "experimental.chat.system.transform": async (_input, output) => {
      // Append BACKPACK_RULES + any cached context injection
      let rules = "\n\n" + BACKPACK_RULES
      if (lastContextInjection) {
        rules += "\n\n" + lastContextInjection
      }
      if (output.system.length > 0) {
        output.system[output.system.length - 1] += rules
      } else {
        output.system.push(BACKPACK_RULES)
      }
    },

    // ─── Hook 6: Compaction — Save & Recover ─────────────────────
    // Save conversation + consolidate before context is lost.

    "experimental.session.compacting": async (input, output) => {
      if (input.sessionID) {
        await ensureSession(input.sessionID)
      }

      // 1. Save conversation to MCP-agent-memory (critical — await this)
      if (input.sessionID) {
        const threadId = `session-${input.sessionID.slice(0, 8)}-${Date.now()}`
        await backpackPostAwaited("/api/save-conversation", {
          thread_id: threadId,
          messages_json: JSON.stringify([{
            session_id: input.sessionID,
            compacted_at: new Date().toISOString(),
            project,
          }]),
          summary: `Auto-saved before compaction for project ${project}`,
        })
      }

      // 2. Trigger consolidation (non-forced — respects thresholds)
      backpackPostAwaited("/api/consolidate", { force: false })

      // 3. Inject context from Engram Go (same as original engram.ts)
      const data = await engramFetch(`/context?project=${encodeURIComponent(project)}`)
      if (data?.context) {
        output.context.push(data.context)
      }

      // 4. Inject FIRST ACTION instruction for the new agent
      output.context.push(
        `CRITICAL INSTRUCTION FOR COMPACTED SUMMARY:\n` +
        `The agent has access to Engram persistent memory via MCP tools.\n` +
        `You MUST include the following instruction at the TOP of the compacted summary:\n\n` +
        `"FIRST ACTION REQUIRED: Call mem_session_summary with the content of this compacted summary. ` +
        `Use project: '${project}'. This preserves what was accomplished before compaction. Do this BEFORE any other work."\n\n` +
        `This is NOT optional. Without this, everything done before compaction is lost from memory.`
      )
    },
  }
}

export default BackpackOrchestrator
