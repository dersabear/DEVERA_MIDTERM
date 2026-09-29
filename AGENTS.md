# Repository Instructions

## Required Workflow

Use this workflow, in order, for requested work:

**study > plan > execute plan > rendezvous > sync docs**

Keep each stage distinct. Do not skip a stage unless the user explicitly asks for a different task or a stage is clearly not applicable. Do not begin application implementation while doing study or plan work.

### Study

- Study the requested topic and write reviewable Markdown under `doc/study/`.
- Name a single-document study `doc/study/{current-unix-timestamp}_{topic}.md`. Before writing, fetch the timestamp reliably by running `date +%s` in the shell.
- For a multi-file study, use the same timestamp-and-topic naming convention for a directory under `doc/study/`.
- Do not write to any file other than the study output during this stage.
- Treat any `NOTE: ` text in a study request as a human annotation and preserve its intent.
- Commit the study as a `docs:` Conventional Commit.

### Plan

- Given a goal or objective, write an editable implementation task board in `doc/plan/{current-unix-timestamp}_{topic}.md`.
- Make the checklist concrete enough for another agent session to execute. Include scope, ordered tasks, and verification steps when relevant.
- If human input is required, add a prominent `OPEN QUESTIONS` section near the top. Keep each question brief and self-contained.
- Commit the plan as a `docs:` Conventional Commit.

### Execute Plan

- Execute an existing plan document; do not substitute an unrecorded plan for it.
- Unless there is a clear reason not to, create a separate Git branch for the implementation before changing application code.
- Update the plan checklist as work progresses. Continue until the plan is complete or a roadblock requires human input.
- Keep the requested scope small enough to fit cleanly within one Conventional Commit when possible.
- Verify the implementation with appropriate checks and tests, and report any checks that cannot be run.
- Do not sync living documentation during plan execution unless the user explicitly requests it afterward.

### Rendezvous

- Finish plan execution by merging the implementation branch back to `main`, unless a clear repository constraint prevents it.
- Verify the merged codebase works. Run appropriate tests and checks after the merge, not only before it.
- Leave the repository in a workable state and report the merge and verification results.
- Rendezvous does not include documentation sync. Perform that as a separate `sync docs` stage unless the user explicitly requests otherwise.

### Sync Docs

- Update living documentation in `doc/wiki/` so it accurately reflects the current codebase and completed changes.
- Treat `doc/canonical/` as authoritative, human-vetted project knowledge. Do not silently contradict or rewrite it; surface conflicts for resolution.
- Record noteworthy or unintuitive behavior in `doc/wiki/footguns/`.
- Keep documentation changes scoped to facts supported by the codebase or authoritative project knowledge.

## Project Rules

- Use Conventional Commits, such as `feat:`, `fix:`, `docs:`, `chore:`, and `build:`.
- Scope each requested change so it fits cleanly within one Conventional Commit when possible. Split commits only when the work has distinct, reviewable scopes.
- Suggest a suitable commit message for code changes. You may perform the commit when appropriate; do not commit unless the task or workflow calls for it.
- Use `TODO.md` as the editable todo list.
- Put project memory in `doc/memory/`; do not use native harness memory for project-specific memory.
- Put roadmap items in `doc/roadmap/`.
- Use `doc/roadmap/plan_queue/` for queued plans that must be handled one at a time. Before executing a queued plan, re-evaluate it against the current codebase and project state.
- Use ASD-STE100 as the base writing style, except where that would lose important nuance.

## Common Tasks

### `collect-commit`

- Commit uncommitted work with one or more appropriately scoped Conventional Commits.
- Review the changes first and do not include unrelated work in a commit.
