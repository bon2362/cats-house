# Family Tree Line Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace post-hoc row connectors with family-block layout and routes whose endpoints always explain a real family relationship or an explicit collapsed branch.

**Architecture:** Convert API graph data into family blocks before coordinate assignment. Layout places measured HTML cards by generation, then a pure router returns paths between card-edge ports, union hubs and continuation markers. The existing page keeps pan, zoom, selection and inspection; it supplies mode and expansion state.

**Tech Stack:** TypeScript, Lit, SVG, Vitest; existing FastAPI tree response unchanged.

**Spec:** `docs/superpowers/specs/2026-10-06-family-tree-line-routing-design.md`

## Global Constraints

- Use existing `unions`, `parent_links.union_id`, hidden-person and mode data; do not infer a missing parent, union or kinship.
- SVG renders bands, routes, hubs and continuation markers only; cards remain in HTML.
- Every route ends at a card edge, union hub or continuation marker.
- Preserve the 6 px click-versus-drag threshold and card popover behaviour.
- Do not add a graph-layout dependency unless deterministic in-repository layout cannot satisfy acceptance fixtures.
- The API contract and the 280-person component remain unchanged.

## Review Focus

- A spouse's parents visibly connect through the spouse and actual union to the selected person.
- A filtered child, partner or union never leaves a free SVG segment.
- Multiple unions keep each child attached to the correct union.
- `all` remains a navigable map rather than a long cross-generation bus.
- Horizontal layout has the same semantics and no card intersection.

---

### Task 1: Build a semantic family-block graph

**Files:**
- Create: `apps/web/src/pages/tree-family-blocks.ts`
- Modify: `apps/web/src/pages/tree-graph.ts`
- Test: `apps/web/test/tree-family-blocks.test.ts`

**Interfaces:**
- Consumes: `TreeGraphData`, `TreeUnionData`, `TreeParentLinkData`.
- Produces: `buildFamilyBlocks(data: TreeGraphData, mode: TreeMode): FamilyBlockGraph`.
- A `FamilyBlock` has `id`, `partnerIds`, `childIds`, `generation`, `sourceUnionId` and `collapsedCount`; a `FamilyEndpoint` is `{ kind: 'card'|'union'|'continuation'; id: string }`.

- [ ] Write failing fixtures for spouse parents, one known parent, a two-child union, two unions of one person and a filtered member. Assert each child belongs to exactly its `union_id`, missing data never creates a partner, and omitted members create `collapsedCount`.
- [ ] Run `cd apps/web && npm test -- tree-family-blocks.test.ts`; expect FAIL because `buildFamilyBlocks` does not exist.
- [ ] Implement `buildFamilyBlocks`: one block per visible union, one single-parent block for a link without `union_id`, original source ID on every duplicated layout card, and collapsed counts only for omitted relationships.
- [ ] Run the focused test; expect PASS.
- [ ] Commit: `git commit -m "feat: model tree family blocks"`.

### Task 2: Place blocks and route semantic edges

**Files:**
- Create: `apps/web/src/pages/tree-layout.ts`
- Modify: `apps/web/src/pages/tree-graph.ts`
- Test: `apps/web/test/tree-layout.test.ts`

**Interfaces:**
- Consumes: `FamilyBlockGraph`, `CardMetrics`, `{ direction: 'vertical'|'horizontal' }`.
- Produces: `layoutFamilyBlocks(graph, options): GraphLayout` with `nodes`, `unions`, `continuations`, `bands`, `paths`, `width`, `height`.
- `GraphPath` becomes `{ kind: 'partner'|'parent-child'|'continuation'; from: FamilyEndpoint; to: FamilyEndpoint; d: string }`.

- [ ] Write failing tests for the spouse-parent path, shared child bus, multiple unions, a one-parent family, unequal card widths and both directions. Assert non-overlapping cards, valid endpoints, true partner/children hub and no route through a non-endpoint card.
- [ ] Run `cd apps/web && npm test -- tree-layout.test.ts`; expect FAIL because `layoutFamilyBlocks` does not exist.
- [ ] Implement deterministic generation placement: partner/children blocks remain contiguous; actual card sizes reserve channels; partner and parent-child lines meet the same union hub; omitted entities become continuation endpoints. Rotate ports and placement rather than changing semantics for horizontal direction.
- [ ] Update `cats-tree-graph` to render endpoint-aware routes, hubs and accessible continuation buttons; cards remain in HTML and duplicated cards dispatch original `personId`.
- [ ] Run `cd apps/web && npm test -- tree-layout.test.ts tree-graph.test.ts`; expect PASS.
- [ ] Commit: `git commit -m "feat: route family tree through union hubs"`.

### Task 3: Make continuations navigable in every mode

**Files:**
- Modify: `apps/web/src/pages/tree-page.ts`
- Modify: `apps/web/src/pages/tree-graph.ts`
- Test: `apps/web/test/tree-page.test.ts`

**Interfaces:**
- Consumes: `continuation-select` event with `{ blockId: string; sourcePersonId: string }`.
- Produces: `expandedBlockIds: Set<string>` passed to `cats-tree-graph`; URL keeps person, mode, depth and direction.

- [ ] Write failing tests that continuation expands only its related family block, does not open a person popover, and preserves pan/zoom/navigation. Add an `all` fixture where distant blocks yield continuations rather than blank-ended routes; search and re-centering remain available.
- [ ] Run `cd apps/web && npm test -- tree-page.test.ts`; expect FAIL because expansion state and event handling do not exist.
- [ ] Implement expansion state reset on root, mode and response changes. Handle the event without selecting a person. Give each continuation a Russian accessible count label. Dragging a continuation more than 6 px must not activate it.
- [ ] Run the focused page test; expect PASS.
- [ ] Commit: `git commit -m "feat: expand collapsed tree branches"`.

### Task 4: Real-data acceptance and regressions

**Files:**
- Modify: `apps/web/test/tree-graph.test.ts`
- Modify: `apps/web/test/tree-page.test.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: local API at `http://localhost:8000` and the worktree Vite UI.
- Produces: reproducible visual acceptance instructions for the Pётр Кошкин scenarios.

- [ ] Add regression fixtures for every Review Focus case; document local checks for spouse-parent route, no dangling descendant line, all-family navigation, horizontal mode, long names and click-versus-drag.
- [ ] Run `cd apps/web && npm test -- tree-family-blocks.test.ts tree-layout.test.ts tree-graph.test.ts tree-page.test.ts`; expect PASS.
- [ ] Visually inspect Peter Nikolaevich Koshkin in `close`, `descendants` and `all`; verify Maria's-parents path, no dangling descendant route and meaningful all-family continuations.
- [ ] After final code change, run:

  ```bash
  /Users/ekoshkin/Cat's House/apps/api/.venv/bin/pytest -q
  cd apps/web && npm test
  cd apps/web && npm run typecheck
  cd apps/web && npm run build
  ```

  Expect every command to exit 0.
- [ ] Request independent code review, then commit: `git commit -m "test: cover family tree line routing"`.

## Self-review

- Task 1 covers semantic blocks, missing parents, hidden members and multiple unions.
- Task 2 covers measured geometry, every endpoint and both directions.
- Task 3 covers mode boundaries, continuations and preserved interactions.
- Task 4 covers real-data acceptance and all regression checks.
- No API change is planned because the necessary data already exists.
