# 2026-09-12 편집 초안 입력·제작 검증

## 실행 경로와 입력 경계

Press v0.4의 기존 `press_revision.py` 기본 경로는 `load_revision` → `read_archive`에서 검수 ZIP의 `FILE_MANIFEST.json` 또는 `delivery_manifest.json`, `DELIVERY_STATUS.json`, 회차 25문항에 대한 5역할 125개 검수 패킷과 해시·상태를 요구한다. 이번 네 ZIP에는 이 manifest와 검수 패킷이 없다. 따라서 기존 경로에서는 `AMBIGUOUS_OR_MISSING_MANIFEST`로 거부되며, 문서상 일반 ZIP 지원을 실제 실행 가능으로 해석하지 않는다. 기존 검수 ZIP의 검증 조건은 바꾸지 않았다.

별도 `--input-kind editorial-draft` 경로는 아래 네 **정확한 원본 ZIP 바이트**만 받는다. `profiles/editorial-draft-sources.json`이 ZIP 전체와 각 항목의 SHA-256을 고정한다. 추출 없이 중복 항목, 절대·상위 경로, 심볼릭 링크, 항목 누락, 크기와 변조를 거부한다. `items.json`, `item_specs.json`, `blueprint.json`, `student_items.json`을 Forge 스키마·문항 게이트 및 회차·문항 번호·배점·5선지·정답·학생뷰 일치로 검증한다. 학생 문제지 입력은 `student_items.json`의 `student_view`만 사용한다. `READ_FIRST.md`는 미해결 편집 단서의 출처로만 기록하며 기계 승인 증거로 사용하지 않는다.

| 회차 | 원본 ZIP SHA-256 | 입력 무결성 | 청사진 상태 |
| --- | --- | --- | --- |
| M01 | `24e6c0d30720017426f161939eefa0ce9e6a79a7772fe21cead4b2cff2005d8d` | PASS, 25문항·50점 | 검사 통과 |
| M02 | `b50adb4c74c0c34e20c681f27c53ad137ddd52d7c3a6fce8c8d1c0ef9365a8a7` | PASS, 25문항·50점 | `CURRICULUM_COVERAGE` HOLD |
| M03 | `2c9990e703ecae176bd27cd4423b2de25c3b694f6d1a8cd5b7465e35f57f9abe` | PASS, 25문항·50점 | `CURRICULUM_COVERAGE` HOLD |
| M04 | `62dc1705ab2f983a6beff9cb0eb36760fb2dbd3c2dc0c817c2a0ce49c79574cd` | PASS, 25문항·50점 | `CURRICULUM_COVERAGE` HOLD |

각 ZIP의 파일별 실제 해시와 상태는 로컬 `work/editorial-intake-20260912.json`에 남겼고, 제작물의 `input-packet.json`, `source-input.zip`, `return-manifest.json`에도 입력 결합 정보가 있다. 이 입력은 `content_status=NOT_REVIEWED`, `input_integrity=PASS`, `press_status=DRAFT_FOR_HUMAN_REVIEW`, `human_release_approval=null`이다. Forge의 Press 1.1 통합사회 판정 `UNSUPPORTED`와 코드 `PRESS_CONTRACT_UNSUPPORTED_SUBJECT`를 확인해 기록했다. 로컬 조판 경로는 공식 Forge→Press 출고 계약이 아니다.

## 실제 제작 범위

M04의 현재 자료 해시와 원문 줄을 기준으로 21개 도판 요청의 모드·선택 줄을 새로 정한 뒤, `work/M04-editorial-20260912-r1-visual-plan.json`으로 제작했다. 일치하는 기존 전용 도식 네 종류만 재사용했고, 나머지는 원문 표 또는 보조 도식으로 처리했다. 해시가 달라진 자료에 과거 설정을 적용하면 `VISUAL_PLAN_STALE`로 거부한다. 표는 선택한 원문 줄만 치환하고, 보조 도식은 원문을 유지한다. 이 방식은 수치·단위·범례를 원문에 결합하지만, 그림의 의미 판단이나 공식 계약 지원을 입증하지 않는다.

Press 코드 커밋 `3587a04880a988ce57cbaaa756138cb7f95fa9be`에서 M04 `build` → 한컴오피스 한글 COM 실제 렌더 → 전쪽 확인 → `seal` → `verify`를 완료했다. 파일럿 1쪽, 학생용 9쪽, 교사용 5쪽이다. 학생용 25문항·21개 도판에 대한 기계 검증은 PASS였으며, 페이지 이미지로 학생용 9쪽과 교사용 5쪽을 모두 확인했다. 문항 1~25의 순서·5선지, 주요 표 수치·단위·범례와 지도·흐름 도판, 학생용의 노골적인 정답·해설 표지를 대조했다. 기술적 반환 manifest는 파일 201개의 크기·SHA-256을 검증하며 상태는 `DRAFT_FOR_HUMAN_REVIEW`, 사람의 출간 승인은 비어 있다.

- 학생용 PDF: `work/M04-editorial-20260912-r1-draft/student/exam.pdf`, SHA-256 `bfa065955bbe2e839f283b117959f085c60d1027bbe61686f0d13e41c59e89a8`
- 교사용 PDF: `work/M04-editorial-20260912-r1-draft/teacher/solutions.pdf`, SHA-256 `544e8f4313be032fabb864003f48c51877bdf5dae3a77ab8fbddcc058a7f2d40`
- 기술적 봉인 ZIP: `work/M04-editorial-20260912-r1-draft.zip`, SHA-256 `8d84d1806b7ed28ca7d21f58a097d39604bac250659a9d7cdd629da602fc46c0`

학생용 9쪽은 6쪽 목표를 넘지만 원문 삭제·글자 축소로 맞추지 않았다. 일부 글 자료가 보조 도식에 중복되어 지면을 차지하므로 시각 편집을 더 다듬어야 한다. M01 Q15, M02 Q18, M03 Q04, M04 Q11·Q14·Q22의 어투 단서가 원본 안내에 남아 있다. 네 회차의 나머지 문항 독립 전수 검수, 저자 근거·정답·교과 판단, M02~M04 교육과정 영역, 모든 도판의 의미 검수와 사람의 출간 승인은 별도 작업이다. 발견되는 내용 오류는 정확한 문항 ID·원본 ZIP 해시·문항 해시와 함께 Forge에 반송해야 하며 Press가 원고를 임의 수정하지 않는다.

## 회귀 검증

`python -X utf8 -m pytest --integration -q`: **160 passed, 2 skipped**. 기존 manifest·125패킷 경로와 새 경로를 함께 실행했다. 새 테스트는 ZIP 누락·변조·중복·경로 탈출, 학생뷰/정답/배점 불일치, 구형 도판 계획, 학생용 정답 표지, HOLD/반환 manifest의 READY 오표시를 거부한다. 과거 원고·검수·승인 파일 및 Forge 저장소는 변경하지 않았다. GitHub 게시·병합은 하지 않았다.
