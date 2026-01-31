# QA Feedback Triage Todo

## Status
- Some items completed; keep this as a rolling QA checklist.

## Phase 1 - Gather Repro & Context
- [ ] Confirm current branch/state and any local diffs
- [ ] Reproduce each issue from testing_feedback.md
- [ ] Record exact reproduction steps for each issue
- [ ] Capture expected vs actual behavior per issue
- [ ] Identify affected files/modules for each issue

## Phase 2 - Root Cause Analysis
- [x] Investigate level-up stat banking logic
- [x] Investigate unequip logic in inventory/gear
- [x] Investigate fuse naming logic (prevent repeated "Fused")
- [x] Investigate flee escape chance logic
- [x] Investigate defend action flow/turn progression

## Phase 3 - Fix Plan & Implementation
- [x] Define data/logic changes per issue
- [x] Implement fixes in priority order
- [ ] Add tests or debug checks where feasible
- [x] Update any related UI text

## Phase 4 - Verification
- [ ] Re-test all 5 QA issues
- [ ] Validate no regressions in combat/menus
- [ ] Update testing_feedback.md with results

---
## Notes
- [ ] 2026-01-31: Created QA triage todo from testing_feedback.md.

- [x] 2026-01-31: Implemented fixes for banked points, unequip toggle, fusion naming ranks, flee chance, and defend flow.
- [x] 2026-01-31: Phase 3 implemented: banking, unequip toggle, fuse naming ranks, flee chance, defend flow, UI updated.
