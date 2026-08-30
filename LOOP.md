# Loop Configuration — Minimal Triage (Claude Code)

## Active Loops

| Pattern | Cadence | Status | Command |
|---------|---------|--------|---------|
| Daily Triage | 1d | L1 report-only | `/loop 1d Run $loop-triage` |

## Human Gates

- No auto-fix until L2 checklist complete
- All high-risk paths: human review required (see ./docs/safety.md denylist)

## Worktrees

- Use `isolation: worktree` when spawning implementer sub-agents (L2+).
- One worktree per fix attempt; discard after verifier REJECT.

## Connectors (MCP)

- MCP optional for L1 report-only loops.
- For L2+: GitHub MCP to read CI/issues; scope connectors to read + comment only until trusted.

## Gedaechtnis

| Datei | Lebensdauer | Wer schreibt |
|-------|-------------|--------------|
| `STATE.md` | wird jeden Lauf neu geschrieben | Loop |
| `loop-cursor.json` | Wasserzeichen + bekannte Befunde, fortlaufend | Loop |
| `loop-run-log.md` | append-only, 30 Tage | Loop |
| `loop-critique.md` | append-only, nie gekuerzt | Loop |
| `loop-decisions.md` | dauerhaft | **nur Mensch** |

Der Loop faengt damit nicht bei null an: Er weiss ueber `loop-cursor.json` genau,
bis wohin er zuletzt geschaut hat, und ueber `loop-decisions.md`, was bereits
entschieden ist.

## Budget

- Max sub-agent spawns per run: 0 (L1)
- Review STATE.md daily

## Links

- Pattern: [daily-triage](https://github.com/cobusgreyling/loop-engineering/blob/main/patterns/daily-triage.md)
- Checklist: [loop-design-checklist](https://github.com/cobusgreyling/loop-engineering/blob/main/docs/loop-design-checklist.md)