# Agent Guardrails and Workflow

This repository uses agent assistance (Codex CLI). The rules below apply to ALL work in this repo.

Scope: This AGENTS.md applies to the entire repository.

## Do Not Push To `main`
- Never push directly to `main`.
- Always create a feature branch and push there.
- Only merge to `main` via a Pull Request (PR) after human review.

## Branching
- Create branches using a short, descriptive prefix:
  - `feat/<short-topic>` for new features
  - `fix/<short-topic>` for bug fixes
  - `chore/<short-topic>` for maintenance
  - `docs/<short-topic>` for documentation-only changes
- If the user asks to “push,” confirm the target branch. Default to creating/pushing a feature branch and (optionally) opening a PR.

## Commits
- Keep commits focused and descriptive.
- Use present tense, imperative mood. Example: `Fix reminder user fetch fallback`.
- Avoid committing unrelated changes.

## Pull Requests
- Open a PR for every change to be merged into `main`.
- Include a concise summary of:
  - What changed
  - Why it changed
  - How to test
- Request human review before merge.

## Approvals and Safety
- Treat any network or repository‑writing actions as requiring explicit user approval when uncertain.
- Ask before running potentially destructive actions (e.g., `git reset`, deleting files/data).

## Testing and Validation
- Run only the minimal necessary tests/linting to validate the change when requested or when it materially impacts behavior.
- Prefer targeted checks near modified code.

## Planning and Communication
- For multi‑step tasks, share a brief plan and keep it updated as work progresses.
- Keep messages concise and actionable.
- When in doubt about scope, assumptions, or branch targets—ask first.

## Exceptions
- The only exception to “no push to main” is when a human explicitly instructs: “Push to main.” Otherwise, assume PR workflow.

---
If any rule here conflicts with a direct user instruction in the conversation, the user instruction takes precedence. When you notice a conflict, confirm with the user before proceeding.
