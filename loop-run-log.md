# Loop Run Log — Arbeitszeiterfassung

Append one entry per run. Prune entries older than 30 days.

## Format

```json
{
  "run_id": "2026-06-09T08:15:00Z",
  "pattern": "daily-triage",
  "duration_s": 45,
  "items_found": 4,
  "actions_taken": 1,
  "escalations": 0,
  "tokens_estimate": 52000,
  "outcome": "report-only | fix-proposed | escalated | no-op"
}
```

## Recent Runs

<!-- Loop appends below this line -->
```json
{
  "run_id": "2026-08-30T16:34:03Z",
  "pattern": "daily-triage",
  "duration_s": 38,
  "items_found": 2,
  "actions_taken": 0,
  "escalations": 0,
  "tokens_estimate": 24000,
  "outcome": "report-only"
}
```

```json
{
  "run_id": "2026-08-30T16:51:09Z",
  "pattern": "daily-triage",
  "duration_s": 210,
  "items_found": 5,
  "actions_taken": 0,
  "escalations": 1,
  "tokens_estimate": 47000,
  "outcome": "report-only"
}
```

```json
{
  "run_id": "2026-08-30T17:30:24Z",
  "pattern": "daily-triage",
  "duration_s": 90,
  "items_found": 0,
  "actions_taken": 0,
  "escalations": 0,
  "tokens_estimate": 20000,
  "outcome": "no-op"
}
```

```json
{
  "run_id": "2026-08-31T05:10:24Z",
  "pattern": "daily-triage",
  "duration_s": 120,
  "items_found": 0,
  "actions_taken": 0,
  "escalations": 1,
  "tokens_estimate": 30000,
  "outcome": "report-only"
}
```
