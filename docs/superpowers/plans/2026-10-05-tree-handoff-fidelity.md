# Family Tree Handoff Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current generic SVG diagram with the approved interactive family-tree workspace and preserve family membership from GEDCOM through to the graph API.

**Architecture:** Store the source family (union) on every parent-child relation, then expose it in the public tree response. Build layout around union hubs and generation bands rather than sorted rows. The page owns pan, zoom, focus history and controls; the graph component renders the positioned scene and card interactions.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL, Lit, TypeScript, SVG, Vitest, pytest.

**Spec:** `/Users/ekoshkin/Cat's House/docs/specs/family-tree-open-source-product-design.md`; `/Users/ekoshkin/Downloads/design_handoff_family_tree/FamilyTree.dc.html`; `/Users/ekoshkin/Downloads/design_handoff_family_tree/Прототип дерева.dc.html`.

## Global Constraints

- The design handoff is the visual and interaction source of truth.
- Preserve unknown and single-parent families without inventing a partner or family membership.
- Use the existing five graph modes and depth limits of 1–5.
- Do not expose private/archive data or credentials.

## Review Focus

- A child of a known couple is attached to that couple’s union hub, not separately to two unrelated parent cards.
- A child with incomplete source data remains visible without an invented union.
- Dragging moves the scene; Ctrl/Command+wheel zooms around the pointer; regular wheel remains page scrolling.
- Fit and centre controls produce usable views after a mode, direction or focus change.
- Card selection, centre change and URL state remain keyboard-accessible.

### Task 1: Preserve family membership end-to-end

**Files:** migration, `apps/api/app/models/genealogy.py`, import/export services, tree service/routes, API tests.

- [ ] Write failing API/import tests for a parent-child link carrying `union_id` and for the public response.
- [ ] Run the focused tests to confirm the missing field causes failure.
- [ ] Add nullable `parent_children.union_id`, populate it from GEDCOM family children, retain it in archive export/import, and return it from `GET /api/v1/tree/{person_id}`.
- [ ] Add a safe one-time local backfill that matches only unambiguous two-parent unions; keep unmatched links null.
- [ ] Run focused tests and the API suite.

### Task 2: Lay out real family groups

**Files:** `apps/web/src/pages/tree-graph.ts`, `apps/web/test/tree-graph.test.ts`.

- [ ] Write failing layout tests for a couple with children, a single-parent link and generation-band metadata.
- [ ] Run the focused test to confirm the generic row layout fails it.
- [ ] Replace alphabetical row placement with union hubs, family blocks and stable generation bands; route marriage and child lines through hubs.
- [ ] Render approved card hierarchy, selected/focus states and the dotted work surface/bands.
- [ ] Run focused graph tests.

### Task 3: Implement the approved workspace interactions

**Files:** `apps/web/src/pages/tree-page.ts`, `apps/web/test/tree-page.test.ts`.

- [ ] Write failing interaction tests for split controls, focus history, pan and pointer-centred zoom state.
- [ ] Run the focused test to confirm it fails.
- [ ] Implement the full-canvas workspace, grouped top/bottom controls, pan, zoom, fit, centre, generation-band toggle and selected-person actions.
- [ ] Keep URL mode/depth/direction/focus state and accessible keyboard control.
- [ ] Run focused page tests.

### Task 4: Verify against the approved handoff and real local data

**Files:** automated tests and local Docker stack only.

- [ ] Run API tests, web tests, typecheck and production build after all code changes.
- [ ] Apply the migration and safe backfill to the local stack only after a database snapshot; import/reload source data if needed to restore exact family membership.
- [ ] Open the real tree at `localhost:5173`, verify each interaction in Review Focus, and compare a screenshot to the approved prototype.
- [ ] Request one final code review, open a PR, and merge only when tests and visual acceptance both pass.
