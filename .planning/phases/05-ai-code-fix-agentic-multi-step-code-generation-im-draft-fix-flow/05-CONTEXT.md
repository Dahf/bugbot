# Phase 5: AI Code Fix — Agentic Multi-Step Code Generation in Draft Fix Flow - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Upgrade the Draft Fix button from a context-scaffolding tool (currently opens an empty PR with `.bugbot/context.md` for external tools) to an agentic AI code generation pipeline. Claude reads relevant source code, generates actual fix code, validates it through multiple rounds, and commits the final fix to the PR branch. The existing Draft Fix button, branch creation, and PR opening infrastructure from Phase 3 are reused — this phase replaces the "delegate to external tools" approach with real AI-driven code generation.

</domain>

<decisions>
## Implementation Decisions

### Generation Strategy
- Multi-step agentic loop: Claude generates a fix, validates it, and iterates if issues are found
- Loop triggers (all three, in sequence per round): lint/syntax checks, AI self-review, test results from CI
- Maximum 3 iteration rounds before finalizing
- If all rounds exhausted without a clean fix: submit the best attempt anyway, with a note in the PR body that validation didn't fully pass

### Code Context Scope
- Interactive exploration: Claude can request additional files during the loop (follow imports, read related modules)
- Repo access via local clone (clone into temp directory for fast file reads and grep/search)
- Cap at 15 files read total across all exploration
- Claude's discretion on whether to provide the full file tree upfront or discover structure as needed

### Quality Gates — Lint
- Run the project's actual linter (detect and use whatever linter config the repo has — ruff, eslint, etc.)
- Feed lint errors back to Claude for the next iteration round

### Quality Gates — AI Self-Review
- Claude reviews its own fix for three criteria:
  1. **Correctness vs. bug report** — does the fix actually address the reported bug?
  2. **Side effects** — could the change break anything else in related code?
  3. **Code style consistency** — does the fix match existing codebase conventions?

### Quality Gates — Tests
- Push the fix to the feature branch and check for GitHub Actions CI pipeline
- If CI exists: wait for CI results, feed failures back to Claude for the next round
- If no CI pipeline detected: skip the test validation step entirely

### Commit Strategy
- Only the final version is committed to the branch (squash all iterations into one clean commit)
- PR body includes a collapsible process log section (files explored, rounds taken, what changed per round, validation results)

### User Visibility
- Live progress messages posted in the bug's Discord thread as each step happens (e.g., "Cloning repo...", "Reading files...", "Generating fix (round 1)...", "Running lint...", "Waiting for CI...")
- Fire-and-forget: no cancel button during generation. User can close the PR afterward if unwanted
- Completion notification as a rich embed: files changed, rounds taken, validation results, PR link, diff summary
- Token usage / cost tracking visible in progress messages (per-round counts and running total)

### Claude's Discretion
- Whether to provide the full file tree upfront vs. discover as needed
- Exact progress message wording and timing
- How to detect and invoke the project's linter
- Temp directory management for local clones
- How to structure the collapsible process log in the PR body

</decisions>

<specifics>
## Specific Ideas

- Current Draft Fix already creates branches, opens PRs, and commits `.bugbot/context.md` — Phase 5 builds on top of this existing infrastructure
- The bot should reuse `identify_relevant_files()` as a starting point for the initial file set, then allow Claude to explore further
- "Only Linux CI pipelines" — don't try to run the full app, keep test validation cost-conscious
- Token usage display helps the team monitor API costs in real-time

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-ai-code-fix-agentic-multi-step-code-generation-im-draft-fix-flow*
*Context gathered: 2026-02-24*
