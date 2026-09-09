# 통합사회 Press 입력 계약 v0.1

`press_contract.load_packet(forge_root, campaign_id)`는 Forge의 현재 승인 증거를 읽어
로컬 편집 초안용 `integrated-social-press-input-v0.1` 객체를 만든다. Forge 원본이나
공식 export를 쓰지 않으며 `official_forge_export`는 항상 `false`이다. 현재
`FRG-SOC-2028-M01`의 기존 Press 판정도 그대로 포함하므로 콘텐츠는 승인 상태지만
Press는 `PRESS_CONTRACT_UNSUPPORTED_SUBJECT`에 따른 `HOLD`이다. 이 로컬 계약은 그
상태를 `READY`로 바꾸거나 공식 Press 승인을 발급하지 않는다.

## API

```python
from pathlib import Path
from press_contract import load_packet, validate_packet

forge = Path("../integrated-social-item-forge")
packet = load_packet(forge, "FRG-SOC-2028-M01")
validate_packet(packet, forge)
```

두 함수 모두 성공할 때 Forge를 변경하지 않는다. 읽을 수 없는 파일, 현재 승인과
맞지 않는 source, 계약에 맞지 않는 packet은 `ContractError`를 발생시킨다.
`validate_packet`은 저장 당시 해시만 확인하지 않고 현재 Forge에서 packet을 다시
만든 뒤 전체 객체를 비교한다. 따라서 선택지나 교사용 필드 누락, packet 수정,
원문·명세·blueprint·review·승인 증거 변경을 모두 거부한다.

## Packet 구조

최상위 필드는 다음과 같다.

| 필드 | 의미 |
| --- | --- |
| `schema_version` | `integrated-social-press-input-v0.1` |
| `campaign_id` | Forge campaign ID |
| `subject` | `통합사회` |
| `curriculum_revision` | `2022` |
| `official_forge_export` | 항상 `false` |
| `status` | `build_campaign_status`가 현재 증거에서 계산한 결과 그대로 |
| `items` | blueprint 순서의 25문항 |
| `visual_handoff` | `build_visual_handoff`가 현재 items/specs에서 계산한 18건 요청 |
| `binding` | canonical artifact 해시와 실제 증거 파일의 raw-byte SHA-256 |

각 `items[]` entry는 `number`, `points`, `item_id`, `source_item_sha256`,
`item_revision`, `student_view`, `teacher`, `materials`,
`core_data_relations`만 가진다. `student_view`는 Forge 원문을 그대로 복사한다.
`item_revision`은 원문에 `item_version`이 있으면 그 값을, 그다음 `version` 값을
사용하며 둘 다 없으면 `source_item_sha256`을 content-addressed revision으로
사용한다.

`teacher`에는 `answer`, `rationale`, `solution_steps`, `choice_evaluations`만 있다.
`core_data_relations`도 교사용·내부 검증 정보다. 학생 문제지 생성기는
`student_view`만 학생 본문으로 사용하고 `teacher`와 `core_data_relations`를 학생
출력에 넣지 않아야 한다. `materials`는 자료의 출처·기준 시점·단위 메타데이터이며,
비텍스트 자료 제작은 최상위 `visual_handoff`의 요청과 함께 처리한다.

## Binding 범위

`binding.canonical_artifacts`는 Forge status가 검증한 blueprint, item specs, items,
validation report, review collection, human approval request, campaign approval receipt의
canonical JSON 해시다. `campaign_status_sha256`과 `visual_handoff_sha256`은 두 파생
객체를 결합한다.

`binding.files`는 다음 현재 입력의 실제 파일 bytes를 SHA-256으로 결합한다.

- `data/contracts/press_support.json`
- blueprint, item specs, items, validation report
- 현재 items/specs에 대응하는 review packet manifest와 packet 125개
- final review result 125개, collection report, human approval request
- 문항 승인 25개와 campaign approval receipt

JSON의 의미가 같더라도 공백이나 줄바꿈을 바꾼 source는 기존 packet의 raw-byte
binding과 달라진다. 새 source를 의도적으로 채택하려면 Forge에서 현재 승인 증거를
다시 완성하고 `load_packet`으로 새 packet을 생성해야 한다.

JSON Schema는 `schemas/press_input_v0.1.schema.json`이다. 스키마 검증은 객체 형태와
학생 선택지 5개, teacher 분리, 25문항 및 SHA 형식을 확인한다. Forge public API의
현재 증거 재검증과 전체 재생성 비교가 source 진위와 freshness를 담당한다.

## 반환 v0.1

반환 루트의 `return-manifest.json`은 `integrated-social-press-return-v0.1`,
`status=DRAFT_FOR_HUMAN_REVIEW`, `human_release_approval=null`, `input_binding`,
`files[{path,sha256,bytes}]`를 담는다. 자신을 제외한 모든 파일을 raw-byte SHA로 묶고,
ZIP 자체 해시는 외부 `.zip.sha256`에 적는다. `student/`는 학생용 HWPX/PDF,
`teacher/`는 정답·해설, `preview/`는 실제 PDF의 전 페이지 PNG이다.
검증기는 파일 경로의 중복과 탈출, 파일 누락·추가, 크기와 SHA-256 불일치를 모두
거부한다. build에서 복사한 `runtime.json`과 `reproduction/`도 별도 결합하여 seal 전
변경을 차단한다.

`visual-receipt.json`은 기존 Forge `integrated-social-visual-receipt-v1`을 그대로
준수한다. `status=COMPLETE`는 18개 파일 반환 범위 완료만 뜻한다. `press_commit`은
실제 로컬 코드 커밋이며 `visual-artifacts.json` 경로의 기준 루트는 `figures/`다.
`visual-result.json`은 추가 로컬 편집 정보로, 각 삽입 PNG와 exact source lines를
영수증의 같은 `(item_id,data_id)` 및 명세와 결합한다. 파일 해시와 의미 검토는 별개다.
`font_provenance`는 개별 figure spec에 기록된 파일명·family·style·SHA-256 집합과
정확히 같아야 한다.

학생 본문에서 도판으로 대체한 범위는 명세의 `core_variables.lines`와 정확히
같아야 하며 해당 PNG 바이트가 HWPX BinData에 존재해야 한다. 그 밖의 발문·자료
본문·표 셀·선택지는 HWPX와 PDF 텍스트에 전부 존재하는지 검사한다. 도판 내 글자는
HWPX 문자 객체가 아니며 SVG/명세에서 수정 후 재생성한다. 이는 학생 본문 전체의
페이지 이미지화와 다르다.

양쪽 저장소 반영이 필요한 후속 변경안: 새 계약을 Forge export 대상에 정식
추가하고 CONTENT 역할과 통합사회 자료 문법을 유지하는 지원 승인 절차를 별도
검토한다. 이번에는 Forge 지원 파일·승인 기록을 변경하지 않았다.
