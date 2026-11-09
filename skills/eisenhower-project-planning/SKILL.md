---
name: eisenhower-project-planning
description: "Plan non-trivial projects with Eisenhower matrices at project, module, and subfunction levels, including implementation status and dependencies."
---

# Eisenhower Project Planning

Use this skill for every non-trivial project request that involves implementation scope, architecture, roadmap, prioritization, milestone planning, or deciding what to build next. The user expects Eisenhower planning to be the default for projects across repositories and domains.

## Goal

Produce an actionable plan that connects priority to reality:

1. Identify the project modules or bounded contexts.
2. Build one project-level Eisenhower matrix for the modules.
3. Build an independent matrix for each module's subfunctions.
4. Mark current implementation status using inspected evidence.
5. Show dependencies, implementation waves, completion gates, and unresolved decisions.

Do not treat the matrix as a generic list of desirable features. It is a decision tool for what to do now, what to schedule, what to handle with a temporary process, and what to defer.

## Required workflow

### 1. Inspect before prioritizing

For repository work, inspect the current README/docs, directory structure, manifests, migrations, tests, deployment configuration, and relevant git status before assigning status or priority. Reuse existing architecture decisions and project terminology. For non-repository work, inspect the material supplied by the user and state assumptions.

Do not infer that a feature is implemented merely because it appears in a design document. Separate:

- design/specification exists;
- schema/migration/configuration exists;
- executable API, UI, job, or integration exists;
- runtime verification or business acceptance exists.

### 2. Define the module inventory

Use the smallest useful module boundaries. Prefer business bounded contexts plus the technical foundation and cross-cutting capabilities that block them. Include integration, security/authorization, data migration, reporting, and operational concerns when they are real project work rather than hiding them under a vague "miscellaneous" module.

For each module, identify:

- purpose and outcome;
- upstream/downstream dependencies;
- current implementation status and evidence;
- critical risks or irreversible data decisions;
- candidate subfunctions.

Do not turn a legacy table count, folder count, or vendor feature list into the module plan without validating business responsibility.

### 3. Apply the matrix

Use these definitions relative to the current project stage:

| Quadrant | Meaning | Action |
| --- | --- | --- |
| Q1 | Important and urgent | Do now in the current wave; reduce to a testable minimum slice |
| Q2 | Important but not urgent | Schedule explicitly with dependencies and an owner/outcome |
| Q3 | Urgent but not important | Contain with a temporary procedure, template, automation, or delegated support |
| Q4 | Neither important nor urgent | Defer or reject until value, dependency, or risk changes |

Importance includes shared-data dependency, security, legal/accounting correctness, operational safety, and irreversible migration risk. Urgency includes blocking the next wave, preventing meaningful validation, or an immediate operational deadline. Do not use urgency to reward the loudest request.

Each matrix item should be an outcome or coherent work package, not a vague verb such as "improve system".

### 4. Mark implementation status inside the matrix

Use a visible status marker in the module summary and in each module's subfunction matrix when practical:

- 🟢 **已完成**: executable implementation exists and the relevant verification/acceptance evidence is available.
- 🟡 **部分完成**: design, schema, migration, configuration, or part of the executable path exists, but the end-to-end capability is incomplete.
- ⚪ **未開始**: only a proposal, mapping, backlog item, or naming direction exists.
- 🔵 **待決定／待驗證**: implementation is intentionally waiting for a business, security, data, or integration decision.
- 🔴 **受阻**: a concrete external or technical blocker prevents safe progress; state the blocker and the next unblock action.

Never mark a module complete because its schema or documentation is complete when its user-facing or operational workflow is not. Cite the evidence briefly, preferably with a file path, command result, test, or runtime check.

### 5. Order the waves

After the matrices, provide a dependency-aware implementation order. A typical shape is:

```text
technical foundation -> shared master/data contracts -> identity and authorization
-> core domain records -> first end-to-end transaction -> dependent transactions
-> integrations, reporting, optimization
```

This is a pattern, not a mandatory sequence. Change it when the inspected dependencies or user goals justify it. Define the first vertical slice and its completion gate; do not promise an entire module as the first milestone.

### 6. Surface decisions without inventing requirements

List only decisions that materially change scope, architecture, priority, data model, compliance, or safety. Label them `待決定` or `待驗證`. Make reasonable low-risk assumptions, but do not silently convert a recommendation into a requirement. If a decision blocks safe implementation, stop that branch and present the smallest useful decision request.

## Output structure

For a normal project-planning response, use this structure:

1. Current state and evidence.
2. Status legend and priority criteria.
3. Project-level matrix: every identified module in Q1/Q2/Q3/Q4, with current status.
4. Module inventory and dependency/wave order.
5. One separate four-quadrant subfunction matrix for every identified module, with current status.
6. Completion gates and verification evidence required to move work forward.
7. Open decisions and the next concrete action.

Keep the first response concise enough to use. If the module inventory is large, give every module its own matrix but keep early-wave subfunctions more detailed than deferred work. Use tables where they make the quadrants and status easy to scan.

## Existing planning artifacts

When a project already contains a planning document, update or extend it rather than creating competing plans, unless the user asks for a new version. Preserve project-specific conventions, language, and links. For a repository planning-only request, do not modify application code; writing a planning document is appropriate when the user asks to record the plan or the project convention requires decisions to be documented.

## Boundaries

This skill plans and prioritizes work. It does not by itself authorize external messages, production changes, destructive migrations, credential handling, or implementation changes. Those actions still require the user's request and the applicable project/tool instructions.
