# Press v0.2 validation — 2026-09-08

Generator commit: `f68ef59aa5766b7a25d45ae6e3bef14b199b872a`.

- Full Windows regression suite: 74 passed, including both original revision ZIPs.
- Portable tests run from a fresh temporary copy without Forge/source inputs; GitHub Linux CI passed on the generator commit.
- Independent code review resolved all Important findings. No outstanding Critical/Important findings at final review.
- Three Hancom output iterations. Final source intake, figures, HWPX, PDF text, embedded fonts and all 50 same-column item checks passed.
- Every r1 student/teacher page was opened. Final r3 has pixel-identical M01 pages and all teacher pages; M02 student pages 4 and 8 changed and were opened again. Other M02 pages are pixel-identical.
- M01 Q18 has source-derived response headers; Q20 uses horizontal short choices. M01 Q25 unit and M02 Q12/Q22 headers retain clear grouping.
- Per-item reference comparisons now come from the tracked build command, with exact reference PDF hash and crop mappings.
- Final build replay used copied Forge Python sources and schemas, preserving dirty-source provenance rather than assuming the Forge HEAD alone was sufficient.

| Set | Student pages | Teacher pages | Student PDF SHA-256 | Teacher PDF SHA-256 |
|---|---:|---:|---|---|
| M01 | 10 | 9 | `60df1226a8407256b2e646d2c63627b13f2b0a307b9f37aade7fdcb70399dbb5` | `b5cfe9e3604a021d0f2138b407397a8777dabb3cff1e6d636da1d6faebe975d7` |
| M02 | 9 | 4 | `e20e2c1ec45f9af934fcd9e6890461d0a831531e00f26bf8cb5eb504f2ac1142` | `e68d22bf230b44c2e0822dcea121a20e3120eaeb2543b4b0212f2448da1ff227` |

The target remains approximately six student pages. The supplied long assumptions and answer choices are preserved; no source content or font size was reduced to force that target. This is an editable review draft, not a human publication approval or certification of pixel-identical KICE typography. New map/topology grammars still require implementation and review; audited specialized renderers reject unknown source semantics.
