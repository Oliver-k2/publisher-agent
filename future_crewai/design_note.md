# Future CrewAI Design Note

1차 MVP는 CrewAI를 구현하지 않는다. 하네스의 역할 경계만 나중에 agent/task/crew 구조로 옮기기 쉽게 유지한다.

## 예상 매핑

- `prompts/planner.md` -> Planner agent
- `prompts/outliner.md` -> Outliner agent
- `prompts/writer.md` -> Writer agent
- `prompts/editor.md` -> Editor agent
- `prompts/continuity_checker.md` -> Continuity checker agent
- `prompts/finalizer.md` -> Finalizer agent

## 이전할 수 있는 경계

- `harness/workflow.py`의 메뉴/역할/산출물 매핑은 CrewAI task 정의로 옮긴다.
- `harness/task_builder.py`의 작업지시서 생성 규칙은 task description template로 옮긴다.
- `harness/result_checker.py`의 산출물 확인은 각 task 완료 검증으로 유지한다.

## 보류

- 자동 승인 모드
- 여러 챕터 병렬 생성
- 출판용 DOCX/PDF 변환
