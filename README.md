# Integrated Social Item Press 2028 v0.4

통합사회 Forge의 검토 ZIP을 편집 가능한 HWPX와 한글에서 실제 변환한 PDF로 제작한다. 입력의 조건부 의견과 미승인 상태를 보존한다. 문항 출제·정답 변경·최종 출고 승인은 Forge와 사람의 영역이다. 사용자가 요청한 해설 윤문은 원문 해시에 연결한 별도 교정본으로 적용한다.

## 설치와 테스트

Python 3.13 기준이다. 기본 테스트와 GitHub Actions는 합성 입력만 사용하므로 Forge, 원본 ZIP, 한글 없이 실행할 수 있다.

```powershell
python -m pip install -r requirements.txt
python -X utf8 -m pytest -q
```

전체 회귀 테스트에는 Windows 글꼴, Forge와 M01 r7·M02 r1 원본 검토 ZIP이 필요하다. 경로를 생략하면 저장소 옆 `integrated-social-item-forge`, `outputs/social-language-20260908`을 사용한다. 통합 테스트를 요청했는데 입력이 없으면 오류로 종료한다.

도판 전용 서체는 Git에서 제외되는 `config.local.json`의 `visual_fonts`에 Regular·Italic 파일 경로와 SHA-256을 기록한다. 현재 도판은 Regular를 기본으로 사용하고, 실제 기울임 표기가 필요한 렌더링만 Italic을 요청한다. 설정한 파일이 없거나 해시가 달라지면 다른 서체로 대체하지 않고 제작을 중단한다. 설정이 없을 때만 Windows 기본 한글 서체를 사용한다.

v0.4의 최신 묶음 테스트에는 M01 language-v2-r1·M02 language-v2-r2·M03 higher-v4 ZIP도 필요하다. 기본 위치는 Forge의 `deliveries/2026-09-08-language-v2`이며 `PRESS_DELIVERY_ROOT`로 바꿀 수 있다. 새 `FILE_MANIFEST.json`/통합 검토 기록과 종전 개별 패킷 형식을 모두 검사한다.

```powershell
$env:PRESS_FORGE_ROOT = 'C:/path/to/forge'
$env:PRESS_INPUT_ROOT = 'C:/path/to/review-bundles'
python -X utf8 -m pytest --integration -q
```

## 시험지 제작

실제 PDF 제작에는 Windows, 한컴오피스 한글 COM, FilePathCheckerModule, 함초롬바탕·맑은 고딕·바탕 글꼴이 필요하다. 입력 경로는 자신의 파일로 바꾼다. **제작 코드는 커밋되어 있어야 하며 출력 폴더는 새 경로여야 한다.**

```powershell
python -X utf8 press_revision.py build --archive 'C:/input/review.zip' --forge-root 'C:/path/to/forge' --out work/run-001
```

M01 r7·M02 r1 및 최신 M01 language-v2-r1·M02 language-v2-r2·M03 v4의 검토된 도식 설정을 기본 제공한다. 원문 해시가 달라지면 이전 줄 번호를 적용하지 않는다. 새 회차·수정 자료는 설정을 내보내고 mode, lines, replace를 검토한 뒤 제작한다.

사용자가 특정 제작본의 학생 자료 표현 교정을 명시적으로 요청한 경우 `--student-overlay`로 원문 해시에 결합된 조건별 교정 JSON을 적용할 수 있다. 원본 `input-packet.json`은 유지하고 적용본을 `student-editorial.json`에 보관한다. 발문·선택지·정답은 이 경로로 바꿀 수 없다.
표현 교정으로 지면 흐름이 달라지는 경우 표 자료는 원문 줄과 해시에 결합된 검증용 그림으로 렌더링하여 한컴의 단 배치에 따른 셀 누락을 막는다. 이때 재입력 가능한 원본 계획은 `visual-plan.json`에 유지하고, 교정본 렌더에 실제 사용한 증강 계획과 핸드오프는 `render-visual-plan.json`, `render-visual-handoff.json`에 각각 저장하여 봉인 시 함께 검증한다.

```powershell
python -X utf8 press_revision.py plan --archive 'C:/input/review.zip' --forge-root 'C:/path/to/forge' --out work/visual-plan.json
python -X utf8 press_revision.py build --archive 'C:/input/review.zip' --forge-root 'C:/path/to/forge' --visual-plan work/visual-plan.json --out work/run-002
```

```powershell
python -X utf8 press_revision.py build --archive 'C:/input/review.zip' --forge-root 'C:/path/to/forge' --student-overlay 'C:/input/student-editorial.json' --out work/run-edited
```

`table`, `schematic`, `serif_schematic`, `bar_matrix`, `bar_list`는 정해진 자료 문법으로 재사용할 수 있다. 지도·기후·흐름 등 전용 도식은 단위·축·관계가 검토된 원문/선택 줄/치환 방식에만 허용한다. 새로운 지도 문법에는 별도 구현과 검토가 필요하다. 같은 원문 줄이 반복되면 `{"text":"원문 줄","occurrence":1}`처럼 0부터 세는 출현 순서를 지정한다. 미지원 자료를 임의 도식으로 대체하지 않는다.

## 문항별 형식 대조

build는 25문항 전체 이미지, PDF 해시, 위치·높이와 검토 항목을 item-review에 만든다. 사용자 보유 공식 예시문항 PDF를 지정하면 문항별 나란히 비교 화면도 만든다.

```powershell
python -X utf8 press_revision.py build --archive 'C:/input/review.zip' --forge-root 'C:/path/to/forge' --reference-pdf 'C:/references/official-social-2028.pdf' --out work/run-003
```

기본 대조표에는 제공된 2028 통합사회 공식 예시문항의 정확한 PDF 해시와 M01·M02·M03 대응 문항/좌표가 있다. 다른 PDF·회차에는 --reference-map으로 같은 구조의 JSON을 지정한다. 원본 PDF와 이미지는 Git에 올리지 않는다. 형식 기준은 [KICE_FORMATS.md](docs/KICE_FORMATS.md)에 있다. 가장 가까운 유형을 비교하며 완전 동일성이나 공식 인증을 뜻하지 않는다.

## 출력과 검토

- student/exam.hwpx, exam.pdf: 학생용. 본문·표는 네이티브 편집 가능, 도식은 PNG이며 SVG/명세로 재생성한다. 요청된 학생 자료 교정은 별도 원문 결합 기록으로 적용한다.
- teacher/solutions.hwpx, solutions.pdf, answer-key.txt: 정답·해설. 기본은 원문이며 `--solution-overlay`를 지정하면 주제·정답 해설·오답피하기로 교정한 해설을 출력한다.
- preview: 학생용·교사용·파일럿 전쪽 미리보기.
- item-review/index.html, items.json: 문항별 검토 이미지와 PDF 연결 정보. 자동 상태는 PENDING이다.
- verification.json: 원문 누락·선택지 순서·문항 분할·도식·폰트 검사, 실제 쪽수, 마지막 단 조정, 긴 문항 목록.
- runtime.json, reproduction: Python/패키지/글꼴 해시, 실제 Forge 소스·스키마·변경 상태, Press 코드 사본.

원본 ZIP과 input-packet.json에도 교사용 정보가 있다. 학생에게는 student 폴더만 배포한다. 약 6쪽을 목표로 하되 원문 보존·가독성을 우선한다. 긴 조건을 자동 삭제·축약하지 않는다.

해설 교정의 EBSi 참고 자료, 어투·서술 기준, JSON 구조와 검증 범위는 [SOLUTION_STYLE.md](docs/SOLUTION_STYLE.md)를 따른다. 교정본은 전체 회차·판본·문항 해시와 정답이 일치해야 한다. 원본 교사용 근거는 보존하고 교정 JSON을 출력에 함께 보관한다.

실제 학생용·교사용 PDF 전쪽과 전체 문항을 확인한 뒤 agent-page-review.json에 아래 필드를 기록한다. 숫자 목록은 실제 확인한 **전체 페이지/문항**으로 채운다. 미완성 목록은 봉인할 수 없다.

```json
{
  "exam_pdf_sha256": "학생용 PDF SHA-256",
  "exam_pages_reviewed": [],
  "solutions_pdf_sha256": "교사용 PDF SHA-256",
  "solutions_pages_reviewed": [],
  "item_numbers_reviewed": [],
  "findings": "검토 결과와 남은 한계"
}
```

```powershell
python -X utf8 press_revision.py seal --archive 'C:/input/review.zip' --forge-root 'C:/path/to/forge' --out work/run-003
python -X utf8 press_revision.py verify --out work/run-003
```

봉인은 도식 설정 해시, 도판별 서체 출처, 빌드 시점의 runtime/reproduction 파일, PDF/검토 범위를 확인한다. verify는 반환 명세에 기록된 정확한 파일 집합·크기·SHA-256을 검사하므로 누락·변조·중복 경로·미등록 추가 파일을 거부한다. 내용 정답·시각적 완성도·최종 출고 승인은 별도이며 human_release_approval을 자동으로 만들지 않는다.

## 재현과 이전 경로

반환 묶음에는 실행 당시 Forge Python 파일·스키마를 보관한다. 수정된 로컬 소스도 해시와 함께 보관하고 변경 상태를 명시하며, 이 재현 자료는 build에서 기록한 해시와 다르면 seal을 거부한다. runtime.json의 Press 커밋을 이 Git 저장소에서 체크아웃하고, 묶음의 source-input.zip, visual-plan.json, reproduction/forge를 각각 --archive, --visual-plan, --forge-root로 지정하면 해당 코드/입력을 다시 사용할 수 있다. 같은 Windows/한글/글꼴 환경이 필요하며 다른 환경의 PDF 바이트 동일성을 보장하지 않는다.

이전 승인본 전용 press.py --config 경로는 v0.1 호환용이다. 새 기능은 press_revision.py 경로를 사용한다. [입력 계약](docs/CONTRACT.md), [교정 ZIP 검증](docs/REVISION_INPUT.md)을 참고한다. Forge와 과학 Press는 읽기 전용 참고이며 원본·글꼴·개인 경로·산출물을 Git에 넣지 않는다.

최신 세 회차의 실제 쪽수, 검증 범위와 한계는 [VALIDATION_V04.md](docs/VALIDATION_V04.md)에 있다.
