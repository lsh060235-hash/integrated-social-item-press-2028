# 통합사회 Press v0.1 초기 구현 기록

> 이 문서는 2026-09-08 로컬 초기 구축 당시의 계획과 제약을 보존한 이력이다. 현재 제작·검증 절차는 저장소 루트 `README.md`를 따른다.

**Goal:** 승인된 기존 25문항의 편집/검토 초안과 재현 코드를 만든다.
**Architecture:** 읽기 전용 Forge 어댑터, 자료 명세와 편집형 HWPX, 한글 렌더 및 검증 반환.
**Tech Stack:** Python, python-hwpx, lxml, Pillow/PyMuPDF, pywin32, pytest, jsonschema.
**Spec:** docs/DESIGN.md

## Global Constraints
- Forge·과학 Press·NAS 원본은 읽기 전용이다.
- 초기 구축 단계에서는 GitHub 반영 없이 로컬 `codex/press-v0.1`에서 작업한다.
- 원문·숫자·선택지 순서·배점 보존, 정답·해설 분리, 최종 사람 승인 미발급.
- 원천 파일/폰트/설정/산출물은 Git 제외.

## Tasks
- [x] 1. `press_contract.py`, `tests/test_contract.py`: 현재 승인 증거 재검증, exact-SHA 입력 계약, stale/누락 차단. 먼저 실제 결함 주입 테스트를 실행하여 실패를 확인하고 구현한다. `load_packet(forge_root: Path, campaign_id: str) -> dict`와 `validate_packet(packet: dict, forge_root: Path) -> None`을 제공한다.
- [x] 2. `press_layout.py`, `tests/test_layout.py`: 모든 학생 텍스트/표 셀을 보존하는 자료 파서, 2단 editable HWPX. `build_hwpx(packet, output, item_numbers=None)`를 제공한다. 표/읽기순서/누출 결함을 먼저 검사한다. 한글로 원본 양식과 Q02/Q13 파일럿을 실제 PDF 변환한다.
- [x] 3. `press_visuals.py`, `tests/test_visuals.py`: 18건 도판 명세 및 렌더, Forge v1 영수증 호환. `build_visuals(packet, output_root, press_commit)` 반환. 실제 파일 변조/삭제를 차단한다.
- [x] 4. `press.py`: 입력 검증→파일럿→25문항→한글 PDF→전 페이지 PNG→내용/구조 검증→SHA 묶음. `python press.py build --config config.local.json --out work/run-001`로 재현한다. 새 출력 폴더만 허용한다.
- [x] 5. 전체 지면 및 코드 독립 검토, 결함 수정, 재검증, 한국어 보고서와 미리보기, 로컬 코드 commit 및 결과 해시 결합.

## Execution record
2026-09-08: 새 경로 미존재 확인 후 로컬 독립 저장소 생성. 기존 저장소 미커밋 상태 조사 완료. 공식 PDF 6페이지 전체 이미지 관찰 완료. 한글 12.0.0.4204 COM 시작 및 파일 접근 모듈 등록 성공.

1~3 구현 완료: 현재 승인 25건, raw 증거 284개, visual 18건 재검증. Q02/Q13 파일럿 A3 세로 1쪽 실제 렌더 성공. 두 저장소의 기존 지원/미커밋 상태 유지. 형식만 있는 새 HWPX를 생성하고 원본 양식의 문항/해설/이미지는 가져오지 않았다.

배치 판단: 학생 원고 21,634자이며 공식 참고 PDF 추출 텍스트는 10,530자다(그림 내 텍스트는 추출량 차이 가능). 본문 12pt·자료 11pt를 유지한 초기 조판 12쪽, 간격 축소만 적용한 네이티브 자료 조판 11쪽. 실제 도판을 결합하면 12쪽. 6쪽 맞춤을 위해 조건을 삭제하거나 본문을 일괄 축소하지 않는다.

독립 검토 반영: 도판 display 경로를 receipt의 같은 문항/자료와 결합; native header 구조 수정; 문항별 번호/배점/선택지 기호/순서 검사; PDF 이미지 자체의 픽셀 대조 추가. 남은 실행은 최종 커밋에서 전체 제작, 전 페이지 시각 검토 기록, 봉인이다.
