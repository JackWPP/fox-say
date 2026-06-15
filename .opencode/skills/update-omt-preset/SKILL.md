---
name: update-omt-preset
description: Update oh-my-opencode-slim agent-to-model mappings. Use when the user wants to change which model each specialist agent uses, switch presets, or reconfigure provider assignments for the oh-my-opencode-slim plugin.
---

# Update oh-my-opencode-slim Preset

Workflow to reconfigure which models the oh-my-opencode-slim plugin assigns to each agent.

## Step 1 — Discover available providers and models

Run both commands in parallel:

```bash
opencode models
```

```bash
opencode auth list
```

From the output, build a table of **authenticated providers** and the **model IDs** they offer. Only recommend models from providers the user already has credentials for.

## Step 2 — Read the current config

Read `~/.config/opencode/oh-my-opencode-slim.json` (on Windows: `C:\Users\WPP_JKW\.config\opencode\oh-my-opencode-slim.json`).

Identify:
- Which `preset` is currently active (the `"preset"` field).
- The agent list inside that preset: `orchestrator`, `oracle`, `explorer`, `librarian`, `designer`, `fixer`, optionally `council` and `observer`.

## Step 3 — Ask the user what to change

Present the current mapping as a table (agent → model → variant) and ask which agents they want to reassign. Suggest models only from the authenticated providers discovered in Step 1.

If the user wants a new provider that isn't yet authenticated, tell them to run `opencode auth login` first, then come back.

## Step 4 — Apply the edit

Edit the active preset block inside the `"presets"` object. Preserve all other fields (`skills`, `mcps`, `variant`, etc.) unless the user explicitly asks to change them.

Rules:
- `model` format is always `provider-id/model-id` (e.g. `xiaomi-token-plan-cn/mimo-v2.5-pro`).
- Do NOT touch other presets (e.g. `openai`, `opencode-go`) unless asked.
- If the user wants a brand-new preset name, add a new key under `"presets"` and update `"preset"` to point to it.

## Step 5 — Remind to restart

After saving, remind the user: **quit and restart opencode** for changes to take effect. They can also use `/preset <name>` at runtime to switch between presets without restarting.

## Agent roles quick reference

| Agent | Typical role | Cost guidance |
|-------|-------------|---------------|
| orchestrator | Main coding agent + delegation hub | Use your strongest all-around model |
| oracle | Architecture advice, hard debugging | Strongest high-reasoning model |
| explorer | Codebase scouting, file discovery | Fast & cheap |
| librarian | External docs, web research | Fast & cheap |
| designer | UI/UX implementation | Vision-capable or frontend-strong model |
| fixer | Routine scoped implementation | Fast & cheap |
| council | Multi-model consensus | Strong synthesis + diverse councillors |
| observer | Image/PDF reading (disabled by default) | Vision-capable model |
