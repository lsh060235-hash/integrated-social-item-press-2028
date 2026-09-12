# Editorial Draft Input Implementation Plan

**Goal:** Accept the four exact 2026-09-12 Forge editorial ZIPs for local unapproved Press review without weakening the existing reviewed-ZIP route.

**Architecture:** Keep `read_archive` and `load_revision` as the manifest-and-review-packet route. Add an explicit editorial-draft intake that checks an allowlist of four complete ZIP SHA-256 values, reads every member without extraction, validates the four JSON artifacts against Forge schemas and cross-file identity, derives a local visual request, and returns the existing Press packet shape with unreviewed status. Reuse build, seal, and verify, but make their intake selector explicit and persist it through reproduction. Visual plans are per-current-hash, with no fallback to stale specialized renderers. No Forge source or review/approval state changes.

**Tech stack:** Python 3.13, stdlib ZIP/hash/JSON, existing Forge read-only validators, pytest, Hangul COM, PyMuPDF.

**Scope:** Local code and output only. No GitHub publishing or merging. 25 items, 50 points each. Student content exclusively from `student_items.json`. Technical seal is draft-only.

## Files

- `press_editorial_draft.py`: exact-archive allowlist and cross-artifact validation into Press packet.
- `press_revision.py`: `--input-kind editorial-draft` routing and build/seal replay; existing reviewed path unchanged.
- `profiles/editorial-draft-sources.json`: filenames and exact SHA-256 for the four provided ZIPs, plus manual review clues and source binding.
- `tests/test_editorial_draft.py`: integration and tamper/status/visual leakage tests.
- `docs/EDITORIAL_DRAFT_INPUT.md`, `README.md`: explicit state boundary and actual verified use.
- `work/` and `outputs/`: ignored local reports and representative rendered draft.

## Tasks

1. Verify the four SHA-256 values and archive compositions; capture baseline rejection by `load_revision`.
2. Write failing tests for four successful editorial intakes, complete ZIP digest tamper, duplicate/unsafe names, student-view mismatch after rebinding in an isolated test profile, wrong choice/answer/blueprint, HOLD/approval states, stale visual plan, and no teacher content in student output.
3. Implement strict editorial intake; run focused tests and old intake regressions.
4. Wire explicit CLI selection through plan/build/seal; keep old default unchanged and record exact input-kind in bindings/runtime.
5. Generate per-source-hash visual plans, render one representative round, inspect every student and teacher page, seal and verify. Verify all four inputs and record the remaining material/wording reviews.
6. Run the full relevant suite, review git diff and local artifacts, report precise verified scope and remaining manual work. Do not merge or push.
