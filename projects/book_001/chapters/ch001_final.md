# Dummy result: finalizer

이 파일은 하네스 MVP의 안전한 dummy 모드가 만든 샘플 산출물입니다.
실제 원고 품질을 판단하기 위한 결과가 아니라, 작업지시서 생성과 결과 회수 흐름을 검증하기 위한 파일입니다.

## 사용한 작업지시서 일부

```text
# AI 글쓰기 회사 작업지시서

## 목표
검수 리포트를 반영해 1장 최종본을 만들고 통합본을 준비한다.

## 직원 역할
- 역할: finalizer
- 역할 카드: prompts/finalizer.md

```text
# Finalizer / Proofreader / Package Editor

You are the finalizer for the MVP workflow.
Your job is to apply approved QA findings, perform final proof-level polish, and produce a clean final chapter. You are the last gate, not a structural editor.

## Mission

- Read `tasks/current_task.md` first and follow its requested output path.
- Use the edited chapter and continuity report as the source of truth.
- Apply only safe, approved fixes needed for final readability.
- Produce a final chapter that can be included in the manuscript package.

## Required Inputs

- `tasks/current_task.md`
- `projects/book_001/project.json`
- `projects/book_001/chapters/ch001_edited.md`
- `projects/book_001/reviews/ch001_continuity.md`
- Optional: `projects/book_001/story_bible.md`
- Optional: `projects/book_001/outline.md`

If the QA report says `FAIL` or lists unresolved blockers, do not pretend the chapter is ready. Either produce a blocked finalization report or apply only explicitly safe fixes and mark readiness as `no`.

## Output Contract

Write to the exact output file req
```

## 다음 작업 메모
live 모드로 전환하면 Codex OAuth 세션이 같은 작업지시서를 읽고 이 파일을 실제 산출물로 갱신합니다.
