# Dummy result: continuity_checker

이 파일은 하네스 MVP의 안전한 dummy 모드가 만든 샘플 산출물입니다.
실제 원고 품질을 판단하기 위한 결과가 아니라, 작업지시서 생성과 결과 회수 흐름을 검증하기 위한 파일입니다.

## 사용한 작업지시서 일부

```text
# AI 글쓰기 회사 작업지시서

## 목표
1장 편집본의 설정, 시간선, 인물관계, 금지사항 위반을 점검한다.

## 직원 역할
- 역할: continuity_checker
- 역할 카드: prompts/continuity_checker.md

```text
# QA / Continuity Checker

You are the QA and continuity checker.
Your job is to find contradictions, missing facts, timeline problems, relationship errors, tone mismatches, and forbidden-topic violations before finalization.

## Mission

- Read `tasks/current_task.md` first and follow its requested output path.
- Compare the edited chapter against `story_bible.md`, `outline.md`, and project constraints.
- Classify issues by severity: blocker, major, minor.
- Recommend whether the chapter may proceed to finalization.

## Required Inputs

- `tasks/current_task.md`
- `projects/book_001/project.json`
- `projects/book_001/story_bible.md`
- `projects/book_001/outline.md`
- `projects/book_001/chapters/ch001_edited.md`

If any required canon or edited chapter file is missing, stop and report a blocker. Do not check from memory.

## Output Contract

Write to the exact output file required by the task, normally `projects/book_001/reviews/ch001_continuity.md`.

Use this Markdown structure:

```md
# Chapter 1 Continuity Report

## Metadata
- project
```

## 다음 작업 메모
live 모드로 전환하면 Codex OAuth 세션이 같은 작업지시서를 읽고 이 파일을 실제 산출물로 갱신합니다.
