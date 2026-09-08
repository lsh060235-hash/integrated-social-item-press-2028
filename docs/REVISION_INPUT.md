# 교정 검토 ZIP 입력 v0.1

기존 승인 캠페인 입력과 별도로, 사용자가 제공한 `social-language-review-delivery-v1` ZIP을 편집 검토 초안으로 제작한다. M01 language-r7과 M02 language-r1을 대상으로 한다. 새 문항을 출제하거나 조건부 의견을 해결했다고 표시하지 않는다.

`press_revision.py`는 ZIP 내부 경로·중복·manifest의 모든 파일 SHA 및 크기를 검사한다. items·ItemSpec·Blueprint 해시를 재계산하고 현재 정본으로 5역할 패킷 125건과 visual handoff를 재구성해 첨부된 파일과 비교한다. Forge의 `collect_review_results`로 검수자 분리·현재 문항 및 패킷 해시·solver 응답을 다시 확인한다. 원본 ZIP과 모든 회원 파일 해시를 반환에 결합한다.

새 입력의 `schema_version`은 `integrated-social-press-revision-input-v0.1`이다. 기존 문항 entry 구조에 source_version, edition_label, source_zip_sha256을 추가하며 source status와 blueprint_issue를 보존한다. `official_forge_export`는 false, `human_release_approval`은 null이다. 기존 승인본 영수증과 연결하지 않는다. Forge 원본이나 지원 상태 파일은 수정하지 않는다.

지면은 기존 HWPX 제작 경로를 사용한다. `build_revision_visuals`는 교정판별 원문만 사용하며 기존 M01 도판 경로의 자료 선택을 변경하지 않는다. 도판 display의 `replace_lines`는 정확한 원문 행만 대체한다. 선택적 `insert_before_line`은 정확한 원문 행 앞에 도판을 추가하고 해당 원문을 네이티브 텍스트로 유지한다. 두 방식을 동시에 지정할 수 없다. 삽입 지점은 figure spec에도 결합하고 이미지 픽셀·문항 위치를 검증한다.

## 실행

Windows 한글 COM, 함초롬바탕·맑은 고딕과 README의 의존성이 필요하다. 생성 코드는 로컬 Git 커밋 상태여야 한다. 입력 ZIP은 수정하지 않는다. `--out`에는 매번 새로운 폴더를 지정한다.

```powershell
python -X utf8 press_revision.py build --archive "<첨부 ZIP 절대 경로>" --out work/M01-language-r7-new
```

`student/`는 문제지, `teacher/`는 정답·해설, `preview/`는 전 페이지 PNG다. 입력 ZIP, 패킷과 teacher/는 정답 정보를 포함하므로 학생 배포는 student/ 파일만 사용한다. 기본 출력은 원문 해설을 보존한다. 사용자가 요청한 해설 윤문은 v0.3의 `--solution-overlay`로 명시적으로 적용한다. 정답·문항은 그대로 두며 기준과 계약은 [SOLUTION_STYLE.md](SOLUTION_STYLE.md)에 있다.

모든 문제지·해설 PNG와 문항별 대조 이미지를 확인한 후 `agent-page-review.json`에 exam_pdf_sha256, exam_pages_reviewed(1부터 마지막까지), solutions_pdf_sha256, solutions_pages_reviewed, item_numbers_reviewed(전체 25문항)를 기록하고 아래 명령으로 반환 묶음을 만든다. 검토 기록은 사람이 했다고 표기하지 않는다. 사람의 최종 출고 승인은 별개다.

```powershell
python -X utf8 press_revision.py seal --archive "<첨부 ZIP 절대 경로>" --out work/M01-language-r7-new
python -X utf8 press_revision.py verify --out work/M01-language-r7-new
```

반환 명세는 `integrated-social-press-return-v0.1`을 재사용한다. source ZIP 해시·판본·원문 해시·도판과 출력 파일 SHA, 재현용 코드, 검증 결과와 미승인 사항을 포함한다. 입력 검증 통과는 조건부 내용·난도·신규성 판정이나 M02 교육과정 포괄 HOLD를 해소하지 않는다.

v0.2는 `FRG-SOC-2028-M` 뒤 두 자리 이상의 회차 번호를 받는다. 입력 신원·125개 검토 패킷 검증은 동일하다. 새 회차 도식은 `plan`으로 내보낸 원문 해시/정확한 줄 선택 설정으로 전달한다. 전용 지도·기후·흐름 렌더러는 검토된 원문에만 허용한다. 반복된 원문 줄 일부만 그림으로 치환하는 설정은 거부한다. 사용 방법과 검증 범위는 저장소 README를 따른다.
