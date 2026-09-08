# Integrated Social Item Press 2028 v0.1

통합사회 Forge의 승인된 FRG-SOC-2028-M01을 편집 가능한 HWPX와 한글에서 실제 변환한 PDF로 제작하는 로컬 초안 제작기이다. 문항 출제 기능은 없다. 기존 과학 Press 1.1의 통합사회 미지원 상태와 Forge 승인 기록을 변경하지 않는다.

## 실행

Windows, 한컴오피스 한글 COM, `FilePathCheckerModule`, 설치된 함초롬바탕·맑은 고딕 글꼴, 옆 경로의 통합사회 Forge가 필요하다.

```powershell
python -m pip install -r requirements.txt
Copy-Item config.example.json config.local.json
# config.local.json에 읽기 전용 Forge 로컬 경로를 설정한다.
python -X utf8 -m pytest -q
python -X utf8 press.py build --config config.local.json --out work/run-001
```

새 출력 경로만 받으며 생성 코드가 로컬 Git에 커밋되어야 한다. 원천 PDF/HWPX/폰트/개인 경로/산출물은 Git에 넣지 않는다. 실행은 GitHub 생성·push·PR·merge·출고 승인을 하지 않는다.

`student/exam.hwpx`는 문단·네이티브 표·일부 PNG 도판으로 구성된다. 본문 전체를 페이지 이미지로 붙이지 않는다. 도판 내부 라벨·값은 SVG/명세로 별도 편집·재생성하며, HWPX 안에서 문자가 아닌 그림으로 들어간 영역은 검증 보고서에 구분한다. 표 형태의 자료 8건은 편집성을 위해 네이티브로 조판하고 별도 반환 도판도 제공한다.

`teacher/solutions.hwpx`, `teacher/solutions.pdf`에는 정답·원문 해설·풀이 단계·선택지 설명을 별도로 담는다. 반환 루트의 `input-packet.json`은 교사용 정보를 포함한다. 학생에게 배포할 때는 `student/` 파일만 사용한다.

전체 `preview/exam` 및 `preview/solutions`를 실제 확인한 뒤, `agent-page-review.json`에 검사한 파일 SHA와 페이지 목록을 기록하고 다음으로 봉인한다. 이 기록은 에이전트의 지면 검토 기록이며 사람의 최종 출고 승인이 아니다.

```powershell
python -X utf8 press.py seal --config config.local.json --out work/run-001
python -X utf8 press.py verify --out work/run-001
```

입력 계약은 [CONTRACT.md](docs/CONTRACT.md), 설계/관찰 근거는 [DESIGN.md](docs/DESIGN.md), 실행 기록은 [PLAN.md](docs/PLAN.md)에 있다. v0.1 도판 어댑터는 M01의 실제 18요청만 지원하며 미지원 데이터/다른 구조는 거부한다. 과학의 SCIENCE 역할 또는 ㄱ·ㄴ·ㄷ 전용 문법을 적용하지 않는다.

## 검증 범위

현재 승인/검수/Blueprint/ItemSpec의 exact SHA, 누락·중복·선택지 수, 소스/학생 출력 대조, 도판 파일과 삽입 바이트 결합, HWPX 재열기·PDF 변환, 실제 용지 방향, 폰트 임베딩, 문항 위치/읽기 순서, 파일 SHA를 확인한다. 테스트는 stale 원문·승인·검수, 변조/누락 도판, 다른 문항 도판 치환, 경로 이탈, 선택지 누락을 주입한다. 해시 일치는 의미 승인이나 사람 승인이 아니다.

## 재사용 출처

- Forge `campaign_status.build_campaign_status`, `build_visual_handoff`, `validate_visual_artifacts`: 기존 읽기 전용 함수 그대로 호출. 계약 경계 유지.
- 과학 Press `make_exam_hwpx.py`, `exam_config.py`: python-hwpx 문단·표·단 설정과 package safety 접근 참고. 코드 전체 복제/직접 import 없음.
- 실제 한글 blank/로컬 제공 양식: native `WIDELY`, width<height가 이 환경의 세로 방향임을 실렌더로 확인. 라이브러리의 PORTRAIT 문자열을 그대로 저장하지 않는다.
- `python-hwpx` API로 신규 문서 생성. 기존 제공 HWPX의 내용/도판/머리말/바탕쪽은 결과에 복사하지 않음.
