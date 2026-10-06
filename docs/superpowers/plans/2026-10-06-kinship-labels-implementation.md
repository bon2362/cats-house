# Kinship Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every person in a tree a verified Russian kinship label relative to the tree centre, including blood and marriage relationships.

**Architecture:** Add a pure API-side kinship resolver that receives people, parent-child edges and unions, returning a typed label, explanation and certainty. `tree_service` computes labels from the complete accessible relationship graph and attaches them to visible tree people; the web client only renders this API result and no longer derives family terms itself.

**Tech Stack:** Python 3.14, SQLAlchemy, pytest; TypeScript, Lit, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-06-kinship-labels-design.md`

## Global Constraints

- Derive labels only from `ParentChild`, `Union`, and recorded sex; never from names, dates or screen position.
- Preserve privacy: archived intermediates may affect a relationship but their names must not appear in explanations.
- Return a neutral, descriptive label when equal valid paths produce incompatible terms.
- Generate readable direct-line prefixes with hyphens: `пра-пра-пра-внук`.
- Do not call `сноха` automatically; use `невестка` with a precise explanation.
- Keep all kinship rules on the API side; the browser must not duplicate genealogy logic.

## Review Focus

- One shared parent must produce `единокровный` or `единоутробный`, never the unqualified `брат/сестра`; covered in Task 1.
- A long direct line must produce the exact number of `пра-` prefixes; covered in Task 1.
- Cousins with unequal distance to their nearest common ancestor must not be mislabeled as same-generation cousins; covered in Task 1.
- A union must not make two unrelated people blood relatives; covered in Task 2.
- An archived intermediary must not leak a name through the API explanation; covered in Task 3.

---

## File Structure

- Create `apps/api/app/genealogy/kinship.py`: pure data types and resolver for one centre/target pair.
- Create `apps/api/tests/test_kinship.py`: unit tests for blood and marriage terminology without a database.
- Modify `apps/api/app/genealogy/tree_service.py`: build complete relationship input, attach resolver output to graph people and path mode.
- Modify `apps/api/app/api/routes/tree.py`: expose typed relationship data in public responses.
- Modify `apps/api/tests/test_public_tree_api.py`: response contract and privacy integration tests.
- Modify `apps/web/src/pages/tree-graph.ts`: render server-provided label and remove `relationshipRole`.
- Modify `apps/web/src/pages/tree-page.ts`: show the explanation in the selected-person inspector.
- Modify `apps/web/test/tree-graph.test.ts` and `apps/web/test/tree-page.test.ts`: verify rendering and no local fallback inference.

### Task 1: Pure blood-relationship resolver

**Files:**
- Create: `apps/api/app/genealogy/kinship.py`
- Test: `apps/api/tests/test_kinship.py`

**Interfaces:**
- Consumes: `KinshipPerson(id: UUID, sex: str | None, is_archived: bool)`, `KinshipParentLink(parent_id, child_id, relationship_type)` and `KinshipUnion(partner_one_id, partner_two_id)`.
- Produces: `resolve_kinship(centre_id: UUID, target_id: UUID, people: dict[UUID, KinshipPerson], parent_links: Sequence[KinshipParentLink], unions: Sequence[KinshipUnion]) -> KinshipResult | None`.
- `KinshipResult` has `label: str`, `kind: Literal['blood-direct', 'blood-sibling', 'blood-collateral', 'affinity', 'descriptive']`, `certainty: Literal['confirmed', 'descriptive']`, and `reason: str`.

- [ ] **Step 1: Write failing blood-relationship tests**

```python
def test_resolves_full_sister_from_two_shared_biological_parents():
    assert result.label == "сестра"
    assert result.reason == "общие родители"

def test_distinguishes_paternal_and_maternal_half_siblings():
    assert paternal.label == "единокровная сестра"
    assert maternal.label == "единоутробный брат"

def test_resolves_three_great_grandchildren_with_hyphens():
    assert result.label == "пра-пра-пра-внук"

def test_resolves_first_and_second_cousins_from_nearest_common_ancestor():
    assert first.label == "двоюродная сестра"
    assert second.label == "троюродный брат"
```

- [ ] **Step 2: Run the blood tests to verify they fail**

Run: `../../.venv/bin/pytest -q tests/test_kinship.py -k blood`

Expected: FAIL because `kinship.py` and `resolve_kinship` do not exist.

- [ ] **Step 3: Implement blood paths in `kinship.py`**

Use breadth-first ancestor maps for centre and target. First classify direct ancestry, then shared-parent sibling cases, then the nearest common ancestor. For equal ancestor distances use `двоюродный`, `троюродный` and word-form equivalents for larger values. For unequal distances of more than one generation return the descriptive relation specified in the design rather than an invented exact term.

- [ ] **Step 4: Add boundary tests for дядя/тётя, племянник/племянница, unknown sex and equal incompatible paths**

```python
def test_returns_descriptive_result_for_equally_short_incompatible_paths():
    assert result.kind == "descriptive"
    assert result.certainty == "descriptive"
```

- [ ] **Step 5: Run the complete kinship unit suite**

Run: `../../.venv/bin/pytest -q tests/test_kinship.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/genealogy/kinship.py apps/api/tests/test_kinship.py
git commit -m "feat: resolve blood kinship labels"
```

### Task 2: Marriage and affinity rules

**Files:**
- Modify: `apps/api/app/genealogy/kinship.py`
- Modify: `apps/api/tests/test_kinship.py`

**Interfaces:**
- Consumes: `resolve_kinship` from Task 1.
- Produces: `KinshipResult.kind == 'affinity'` for relationships through exactly one required union path.

- [ ] **Step 1: Write failing affinity tests**

```python
def test_resolves_spouse_and_childs_spouse():
    assert wife.label == "жена"
    assert daughters_husband.label == "зять"
    assert sons_wife.label == "невестка"

def test_resolves_in_laws_from_centres_sex():
    assert wifes_father.label == "тесть"
    assert husbands_sister.label == "золовка"

def test_resolves_yatrovka_only_for_wives_of_two_brothers():
    assert result.label == "ятровка"

def test_uses_descriptive_affinity_when_required_sex_is_unknown():
    assert result.label == "родственник по браку"
    assert result.certainty == "descriptive"
```

- [ ] **Step 2: Run affinity tests to verify they fail**

Run: `../../.venv/bin/pytest -q tests/test_kinship.py -k affinity`

Expected: FAIL because the resolver currently handles only blood paths.

- [ ] **Step 3: Implement affinity lookup in `kinship.py`**

Evaluate exact patterns in priority order: spouse, spouse of child/sibling, parents and siblings of spouse, then the two-union `ятровка` pattern. Keep the Russian explanation structural (`жена сына`, `жёны двух родных братьев`) even when the primary label is short.

- [ ] **Step 4: Run the complete kinship unit suite**

Run: `../../.venv/bin/pytest -q tests/test_kinship.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/genealogy/kinship.py apps/api/tests/test_kinship.py
git commit -m "feat: resolve affinity kinship labels"
```

### Task 3: Tree API relationship contract

**Files:**
- Modify: `apps/api/app/genealogy/tree_service.py`
- Modify: `apps/api/app/api/routes/tree.py`
- Modify: `apps/api/tests/test_public_tree_api.py`

**Interfaces:**
- Consumes: `resolve_kinship` from Tasks 1–2.
- Produces: optional `relationship` on each non-root `TreePerson` and `TreePersonResponse`; it serializes as `{label, kind, certainty, reason}`.

- [ ] **Step 1: Write failing public API contract tests**

```python
def test_tree_people_include_server_computed_sister_label(client, database_session):
    assert person["relationship"] == {
        "label": "сестра",
        "kind": "blood-sibling",
        "certainty": "confirmed",
        "reason": "общие родители",
    }

def test_tree_relationship_reason_hides_archived_intermediary_name(client, database_session):
    assert "Секретное имя" not in response.text
```

- [ ] **Step 2: Run the public API tests to verify they fail**

Run: `../../.venv/bin/pytest -q tests/test_public_tree_api.py -k relationship`

Expected: FAIL because the response has no `relationship` field.

- [ ] **Step 3: Attach resolver output in `tree_service.py` and expose it in `routes/tree.py`**

Load all parent links and unions needed by the root's connected component for resolution, not merely the visible depth-limited graph. Create `TreeRelationship` and `TreeRelationshipResponse` dataclasses/models with the exact four fields from the interface. Omit the field for the root and for a person with no proven path. Redact archived names when building `reason`.

- [ ] **Step 4: Update path-mode contract tests**

Assert that `relation_path` retains its existing edge labels and additionally returns the same `relationship` object for the selected target.

- [ ] **Step 5: Run the API tree tests**

Run: `../../.venv/bin/pytest -q tests/test_public_tree_api.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/genealogy/tree_service.py apps/api/app/api/routes/tree.py apps/api/tests/test_public_tree_api.py
git commit -m "feat: expose kinship labels in tree API"
```

### Task 4: Render server-computed labels and explanation

**Files:**
- Modify: `apps/web/src/pages/tree-graph.ts`
- Modify: `apps/web/src/pages/tree-page.ts`
- Modify: `apps/web/test/tree-graph.test.ts`
- Modify: `apps/web/test/tree-page.test.ts`

**Interfaces:**
- Consumes: optional `TreePersonData.relationship: { label: string; kind: string; certainty: 'confirmed' | 'descriptive'; reason: string }` from Task 3.
- Produces: card eyebrow text from `relationship.label`; inspector text from `relationship.reason`.

- [ ] **Step 1: Write failing card and inspector tests**

```typescript
expect(role('sister')).toBe('СЕСТРА')
expect(role('unrelated')).toBe('УЧАСТНИК СЕМЬИ')
expect(inspector.textContent).toContain('общие родители')
```

- [ ] **Step 2: Run the web tests to verify they fail**

Run: `npm test -- tree-graph.test.ts tree-page.test.ts`

Expected: FAIL because the browser still derives partial roles locally and the inspector has no reason.

- [ ] **Step 3: Replace local relationship inference with API data**

Extend `TreePersonData`, remove `relationshipRole`, render `relationship.label.toUpperCase()` when present and `УЧАСТНИК СЕМЬИ` otherwise. Add a redacted `Почему так` line to the inspector only when `reason` is supplied.

- [ ] **Step 4: Run targeted web tests**

Run: `npm test -- tree-graph.test.ts tree-page.test.ts`

Expected: PASS.

- [ ] **Step 5: Run full verification**

Run:

```bash
cd apps/api && ../../.venv/bin/pytest -q
cd ../web && npm test && npm run typecheck && npm run build
```

Expected: all API and web tests pass; typecheck and build exit 0.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/tree-graph.ts apps/web/src/pages/tree-page.ts apps/web/test/tree-graph.test.ts apps/web/test/tree-page.test.ts
git commit -m "feat: render computed kinship labels"
```
