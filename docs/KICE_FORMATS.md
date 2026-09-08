# 문항별 평가원 형식 대조

대상: M01 표현교정 r7·M02 표현교정 r1, 총 50문항. 내용 변경 없이 조판 형식만 적용한다.

우선 참조는 사용자 제공 2028 통합사회 공식 예시문항 25개이다. 실제 기출 보조 참조는 2026학년도 수능 생활과 윤리·사회문화·한국지리 문제지다. 공식 CDN의 6월 모평 링크는 다운로드 404여서 실제 수능 문제지는 https://math-son.tistory.com/1563 에 보관된 평가원 원문 사본을 열어 확인했다. 자료 본문·그림을 새 문제지에 복사하지 않는다. 대조는 관찰 가능한 형식의 대응이며 공식 저작권·출고 승인이나 완전 동일성의 인증이 아니다.

구현: 문항 번호만 굵게, 본문 11.5pt, 자료 11pt, 출처 주석 10pt, 조건별 자료 상자 또는 문항별 통합 상자, 표 수치 가운데 정렬과 가변 행 높이, 선지 내어쓰기, 짧은 연결형 선택지 정렬. 자료 상자는 네이티브 편집 가능 셀이며 그 안의 표도 네이티브다. 복합 조항은 문장형 선택지를 유지하고 보기용 진술이 없는 문제에 〈보기〉를 추가하지 않는다.

한글 실제 PDF에서 머리말 가로선·본문 전체 높이 세로선을 확인한다. python-hwpx의 머리말 사본 동기화와 선 좌표 정규화가 필요했다. M02는 25번을 마지막 우단으로 옮겨 균형을 맞춘다. 6쪽 강제 축소보다 원문 보존·가독성을 우선한다.

반복 검토: 1차 기존본 M01 4/10·M02 5/10 → 2차 수정본 각7.5/10. 최종 후보를 실제 한글로 다시 렌더링해 전쪽 대조한다. 검토 원문과 PDF 해시는 반환 묶음에 기록한다.

## Reference layout families

| Code | Official examples | Structural cue |
|---|---|---|
| D | Q1, Q4, Q8, Q13–16 | Distinct speakers, dialogue/position panel, sometimes a separate case. Drawn characters are optional; clear speaker labels are essential. |
| R | Q2, Q10, Q22, Q23 | Report, historical document or source card; material has a title/frame, with images/table nested as appropriate. |
| G | Q3, Q5, Q6, Q9, Q12, Q20, Q24, Q25 | Graph/map/diagram with immediate legend/units/notes, in a deliberate panel. |
| T | Q19, Q21 | Numerical/comparative table plus short contextual material, no unnecessary decorative card. |
| P | Q11, Q17, Q18 | Plain text passage/cases in a fine rectangular panel. |
| V | Q2, Q4, Q9, Q12, Q15, Q18, Q23 | Separate `<보기>` with labeled candidate statements; only use if actual option logic has those statements. |
| A | Q20 (answer matrix); Q2/Q4 (compact combinations) | Aligned response choices, distinct from stimulus tables. |

## M01 — all 25 question formats

Every row also requires the global prompt/material/choice typography fixes above. `+` indicates a hybrid; no exact reference match is claimed where item structure differs.

| Q | Source structure | Closest official reference | Required item-specific layout |
|---|---|---|---|
| 01 | Time/zone record table + 갑/을 inquiry | Q2 R/T + Q8 D | Put record table in a report panel; separate dialogue lines with speaker gutter; scope definition follows as a compact note. Sentence options hang. |
| 02 | Scenario comparison table + lens/rule | Q19 T + Q11 P | One scenario panel with table and a distinct evaluation-criteria paragraph. Avoid repeated unboxed source preambles. |
| 03 | Two dated diary records + comparison scope | Q10 R + Q8 D | Two clearly labeled dated records inside a source card, scope below; current heavy sans mini-card contrasts unnecessarily with serif body. |
| 04 | Before/after survey table + interventions | Q19 T | A titled survey panel; use a wide first/second year comparison with compact cell padding and adequate prose columns. Intervention assumptions separated below. |
| 05 | Two common spatial grids + protection plan | Q2 R/G + Q19 T | Keep resident counts and flood status as clearly paired 2×3 spatial grids or one dual-encoded grid with legend; plan table under them. Do not treat generic rows as an actual map. |
| 06 | Two nature positions + manager report/student claim | Q4 D + Q1 case | One position panel with 갑/을 hanging labels; a separate case/student-claim card. Sentence options. No `<보기>` label. |
| 07 | Container flow fractions + three actors | Q21 G/T + Q13 D | Actual branching flow diagram with no unsupplied derived answer numbers; actor statements in compact aligned rows under it. |
| 08 | Schematic island position/legend + diffusion record | Q5 G + Q9 R | North–south schematic with correct symbols/legend; dated before/after source text inside same frame or a second record panel. |
| 09 | Stratigraphic order + form/function table + transmission record | Q23 R/G + Q2 R | Vertical stratigraphic diagram showing the marker layer; comparison table and transmission statement in a coherent evidence card. Long stem needs normal weight and hanging line start. |
| 10 | Operations ㄱ/ㄴ + evaluation criteria and means | Q8 P/D | Two operation paragraphs inside one panel, criteria/available means visibly separate. These are case labels, not automatically `<보기>` statements. |
| 11 | Language/service spatial overlay + interview + means | Q3 G + Q13 D | Aligned west–east bands for resident/service language; interview/means panel beneath. Preserve distinct service and resident layers. |
| 12 | Four-cell land-use change + migration table | Q9 G + Q19 T | Before/after 2×2 land-use grid with corresponding IDs; compact migration table and notes within a common material panel. |
| 13 | Energy bar data + information-collection rule | Q6 G + Q11 P | Actual grouped horizontal bars with zero baseline/units; policy statements separate. Do not present █ glyphs as finished chart design. |
| 14 | Two-period sales table + claims ㄱ/ㄴ | Q19 T + Q13 inquiry | Survey panel and short claim panel; claims visibly labeled. Since options evaluate claims in prose, do not falsely imitate a standard ㄱ~ㄹ combination question. |
| 15 | Two rights records + incomplete comparison matrix | Q10 R + Q20 A | `(가)/(나)` or existing period labels as two source sections; readable blank matrix; answer matrix needs explicit existing response-field headers. |
| 16 | Work intervals + hypothetical rule/formula | Q21 T + Q11 P | Compact time line or interval table with work/break status; separate rule panel with equations. Three numeric output columns can be aligned. |
| 17 | Two thinkers + two states + mixed paired options | Q1 D/case + Q20 A | Position panel then 1차/2차 case table; options must preserve the long qualifier in ②, so avoid pretending all five are simple two-cell values. |
| 18 | Subregion needs table + allocation rule | Q19 T + Q20 A | Table and rule in one material panel; choices under `가 지역 / 나 지역` numeric headers, compact spacing. |
| 19 | Regime chronology + income/price bars + mixed triple responses | Q17 R + Q6 G + Q20 A | Visually separate regime record, chronology and real chart; long middle response field needs a deliberate wide column or sentence list, not slash-separated run-on text. |
| 20 | Asset availability table + portfolio table + target | Q19 T | Two neatly titled tables in a unified financial-model panel; date/goal assumptions normal body. Very short five choices can run in a compact row. |
| 21 | Three-stage production flow + capacities + compliance | Q21 G/T | R→S→T diagram, capacity and compliance tables grouped tightly; transaction/output response columns. |
| 22 | Revenue/fee flow + two proposals | Q21 G/T + Q8 D | Revenue flow header and numerical proposal table or clearly separated 갑/을 statements; target/assumptions in-panel. Sentence choices. |
| 23 | Three actors' powers + action labels + assignment options | Q13 D + Q20 A | Actor/power panel then clearly separated action panel; aligned action→actor options without inventing a `<보기>` truth-combination instruction. |
| 24 | Two dated sources + historian/ethicist principles | Q10 R + Q13 D | Two source cards labeled 가/나, then compact two-speaker principles panel; full sentence options or adequately wide classification/handling matrix. |
| 25 | Population/household/energy table + goal/formulas | Q24/Q25 G topic, Q19 T structure | Current source is a table, so use a clean numerical table with units and compact formula/goal panel. No need to invent an official-style map. |

## M02 — all 25 question formats

| Q | Source structure | Closest official reference | Required item-specific layout |
|---|---|---|---|
| 01 | Two selection positions + three-alternative index table | Q1 D/case + Q20 A | Position panel with 갑/을 gutters, numerical table below, answer matrix headed 갑/을. |
| 02 | River network + before/after sediment table | Q2 R/G + Q19 T | Existing diagram and table share a material frame, with adjacent unit/flow legend. Compact notes should not repeat map visually as prose without hierarchy. |
| 03 | Culture schematic + records + committee rules | Q3 G + Q7 R | Schematic and `(가)/(나)` investigation records in a report panel; X/Y voting rules in a separate compact policy section. |
| 04 | Two nature positions + hypothetical wetland case | Q4 D + Q1 case | Box the two positions, then separate the changed-case question. Speaker hanging indents, not an uninterrupted paragraph. |
| 05 | Seasonal temperature/rain charts + storage rule | Q5 G | Keep region charts aligned in a shared climate panel with clear same scales/units; storage recurrence conditions in a distinct rule section. |
| 06 | Urban/rural before/after table + reclassification note | Q6 G topic, Q19 T structure | Table panel; reclassification fact in the main stimulus, urbanization definition compact. A chart is not necessary. |
| 07 | Three diffusion records + taxonomy + researcher claim | Q7 R/D | Three labeled record blocks, followed by researcher claim and supplied classification definition. Online-class decoration optional; structural grouping mandatory. |
| 08 | Researchers' cultural evaluations | Q8 D/P | Case panel with clear 갑/을 paragraph boundaries and labels; sentence choices outside. |
| 09 | Before/after travel network + time threshold | Q9 G | Existing before/after route drawings grouped with shared legend, transfer wait visibly attached to B; all time assumptions adjacent. |
| 10 | Historical timeline + declaration rights excerpt | Q10 R | Titled museum/source card with timeline and rights excerpt as two sections, source note at bottom. Avoid only framing the first two lines. |
| 11 | Rights-restriction criteria + city case | Q11 P | Criteria panel plus clearly separated case, preferably same framed material with small subtitle. Sentence options have hanging indents. |
| 12 | Refugee school table + barriers + institutional capacity | Q12 G topic + Q19 T | Readable numerical table and capacity statements in one report card; preserve child counts versus enrolled shares clearly. Institution/country/count choices can form aligned columns if exact wording permits. |
| 13 | Service-location network + positions + project capacities | Q13 D + Q20 A | One diagram/data panel, two-speaker criteria panel and compact project table; answer matrix headed 갑/을. |
| 14 | Civil-disobedience criterion + two organizations | Q14 D/P | Box criterion, separate shared premises from P/Q conduct using paragraph labels. Current continuous dense block is strongly unlike official. |
| 15 | Two justice positions + income/process table | Q15 D + Q19 T + Q20 A | Position panel above table; wider process field with centered numeric cells, reduce tall-cell visual ladder. Answer matrix headed 갑/을. Do not add Venn diagram without matching source logic. |
| 16 | Two distribution standards + production/need data | Q15 D + Q19 T + Q20 A | Standards as two labeled lines, tidy data table. Keep option ⑤ full explanatory text spanning response columns; do not lose its nonpair form. |
| 17 | Historical law background + policy description | Q17 P + Q10 R | Single exhibit/source card with chronology/background and policy sections. Existing tiny boxed leading statement plus unboxed remainder is inconsistent. |
| 18 | Conflict cessation + exclusion/justification case and definitions | Q18 P | Case frame with compact definition section; choices remain five statements. Do not add `<보기>` absent from actual response logic. |
| 19 | Asset table + two goals/opportunity cost + triple choices | Q19 T + Q20 A | One financial model panel; choices headed 목표Ⅰ / 목표Ⅱ / 목표Ⅱ의 기회비용. Units once in header, provided all original values preserved. |
| 20 | Weighted international collaboration network | Q20 G | Existing schematic in one graph panel, with edge-count definition/period/legend. Sentence choices outside. No radar chart is required. |
| 21 | Unit labor table + specialization/trade plan | Q21 T | Table/context in a framed model, then short plan section. Decimal/fraction math should remain legible and consistent. |
| 22 | Historical agreement excerpts + future project table | Q22 R + Q19 T | Numbered article excerpts as a source document card, future decision table as separate panel. Keep historical-vs-future assumptions clearly distinct. |
| 23 | Historical claim/debate + port date table + coordinate map | Q23 R/G | Source/debate card with table and coordinate schematic grouped deliberately, north/east labels and dates readable. Avoid tiny map below long unboxed narrative. |
| 24 | Population/age-share table + dependency definition | Q24 G topic, Q19 T structure | Numerical table panel with percent/count units; compact dependency definition. No map needed for fictional A/B regions. |
| 25 | Total energy/share table + two goals | Q25 G topic, Q19 T structure | Table panel with total versus share headers unmistakable; goals/assumption text grouped under table, hanging choice lines. |

