# AI 글쓰기 회사 하네스 MVP

이 프로젝트는 OpenAI API를 직접 호출하지 않고, ChatGPT 계정으로 로그인된 Codex CLI를 글쓰기 직원처럼 사용하는 로컬 파일 기반 회사 운영 시스템입니다.

사용자는 CEO 역할을 맡아 방향, 장르, 취향, 수정 요청을 입력합니다. 하네스는 작업지시서를 만들고, Codex 실행부에 넘기고, 결과 파일이 지정된 위치에 생겼는지 확인하고, 실행 로그를 남깁니다.

## 실행

```powershell
python main.py
```

처음에는 안전한 `dummy` 모드로 실행됩니다. 이 모드는 실제 Codex를 호출하지 않고 샘플 산출물을 만들어 하네스 흐름만 검증합니다.

메뉴 9번으로 `live` 모드로 바꾸면 하네스가 다음 형태의 명령을 사용할 준비가 되어 있습니다.

```powershell
codex exec --skip-git-repo-check -C <project-root> "<task prompt>"
```

## 메뉴

- 1. 새 책 만들기: 다음 번호의 책 폴더(`projects/book_002` 등)를 만들고 현재 책으로 선택합니다.
- 2. 기획 생성: 현재 선택된 책의 `story_bible.md`를 목표로 작업지시서를 만듭니다.
- 3. 목차 생성: 현재 선택된 책의 `outline.md`를 목표로 작업지시서를 만듭니다.
- 4. 챕터 초안 생성: 현재 선택된 책의 현재 챕터(`chNNN`) 초안을 목표로 작업지시서를 만듭니다.
- 5. 편집본 생성: 현재 챕터의 편집본을 목표로 작업지시서를 만듭니다.
- 6. 설정 검수: 현재 챕터의 검수 리포트를 목표로 작업지시서를 만듭니다.
- 7. 최종본 생성: 현재 챕터의 최종본을 목표로 작업지시서를 만들고, 완료 후 다음 챕터로 진행 상태를 이동합니다.
- 8. 현재 상태 보기: 프로젝트 상태와 산출물 목록을 보여줍니다.
- 9. 실행 모드 변경: `dummy`와 `live`를 전환합니다.
- 10. 책 선택: 기존 책 목록에서 이어서 작업할 책을 선택합니다.
- 11. 완전자동화 모드: CEO 최초 명령 한 번으로 제작 지휘, 기획, 목차, 챕터별 집필/편집/검수/최종화, 최종 원고 패키징까지 순차 실행합니다.

현재 선택된 책은 `projects/current_project.txt`에 저장됩니다. 이 파일이 없으면 기본값으로 `book_001`을 사용합니다.

`outline.md`의 Chapter Table이 있으면 하네스가 총 장 수를 감지해 `project.json`과 `project_status.md`에 반영합니다. 예를 들어 1장이 최종화된 12장짜리 책은 다음 실행 대상이 자동으로 `ch002`가 됩니다.

완전자동화 모드는 최초 명령에서 분량을 추정합니다. `10p 분량의 단편소설`이나 `10p 분량의 1챕터`는 1장 완결로, `300p 분량의 장편소설`은 기본적으로 약 12장 구성으로 계획합니다. 현재 선택된 책을 이어서 만들고 싶으면 최초 명령에 `이어쓰기`, `계속`, 현재 프로젝트 ID, 또는 현재 제목을 포함하면 됩니다.

자동모드는 결과 파일이 존재하는지만 보지 않고 역할별 필수 섹션, `Next Handoff`, `다음 작업 메모`가 있는지 확인합니다. 토큰 소진 등으로 부분 파일만 생기면 같은 단계를 한 번 재시도하고, 그래도 실패하면 `tasks/correction_task.md`를 남긴 뒤 현재 단계에서 중단합니다.

최종본 게이트는 `final_status: READY` 또는 `READY_WITH_NOTES`인 챕터만 완료로 계산합니다. continuity report가 `FAIL`이거나 `proceed_to_finalizer: no`이면 자동모드는 finalizer로 넘기지 않고 같은 챕터의 editor/continuity 단계를 재시도합니다. `BLOCKED` final 파일이 존재하더라도 완료 챕터로 세지 않으며, 다음 챕터 writer는 그 파일을 canon으로 이어받지 않고 이전 edited/review와 outline을 우선 참고합니다.

## 하네스 파일

- `harness/state_manager.py`: 프로젝트 상태 파일 생성, 읽기, 저장
- `harness/task_builder.py`: Codex가 읽을 작업지시서 생성
- `harness/codex_runner.py`: `dummy` 또는 `live` 모드로 실행
- `harness/result_checker.py`: 기대 산출물 존재 여부 확인
- `harness/logger.py`: 실행 결과를 `logs/runs.jsonl`에 기록
- `harness/workflow.py`: 메뉴, 역할, 산출물 경로, 다음 단계 매핑

## 검증

```powershell
python -m unittest tests.test_harness_mvp -v
```

`pytest` 없이 Python 표준 라이브러리만으로 테스트할 수 있습니다.
