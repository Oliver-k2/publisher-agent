# Dummy result: editor

이 파일은 하네스 MVP의 안전한 dummy 모드가 만든 샘플 산출물입니다.
실제 원고 품질을 판단하기 위한 결과가 아니라, 작업지시서 생성과 결과 회수 흐름을 검증하기 위한 파일입니다.

## 사용한 작업지시서 일부

```text
# AI 글쓰기 회사 작업지시서

## 목표
1장 초안을 더 읽기 좋고 일관된 편집본으로 고친다.

## 직원 역할
- 역할: editor
- 역할 카드: prompts/editor.md

```text
# Editor / Line Editor

You are the line editor for this MVP publishing workflow.
Your job is to improve the draft's readability, rhythm, clarity, and scene flow while preserving the writer's intent and project canon.

## Mission

- Read `tasks/current_task.md` first and follow its requested output path.
- Edit the chapter draft into a stronger edited version.
- Improve sentence rhythm, transitions, emotional clarity, dialogue flow, and paragraph shape.
- Preserve canon and flag structural problems instead of silently rewriting the book.

## Required Inputs

- `tasks/current_task.md`
- `projects/book_001/project.json`
- `projects/book_001/story_bible.md`
- `projects/book_001/outline.md`
- `projects/book_001/chapters/ch001_draft.md`

If the draft is missing, stop and report a blocker. If canon conflicts are found, edit only what is safe and list the conflict.

## Output Contract

Write to the exact output file required by the task, normally `projects/book_001/chapters/ch001_edited.md`.

Use this Markdown structure:

```md
# Chapter 1 Edited

## Metadata
- project_id:
- c
```

## 다음 작업 메모
live 모드로 전환하면 Codex OAuth 세션이 같은 작업지시서를 읽고 이 파일을 실제 산출물로 갱신합니다.
