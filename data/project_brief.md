# Library Management System — Project Brief

## Objective
Build a small Library Management System (LMS) for a university library that
supports day-to-day librarian workflows and student self-service.

## Scope (this semester)
A single-library, single-branch system. Web UI out of scope — a command-line
or minimal API surface is acceptable. Multi-tenant, payments and
recommendation features are out of scope.

## Required features
1. **Book search** — search the catalog by title, author or ISBN.
2. **Book issue and return** — record when a student borrows or returns a book.
3. **Student borrowing records** — per-student history of active and past loans.
4. **Overdue book reporting** — generate a list of overdue loans with days
   overdue and the borrowing student.

## Non-functional expectations
- Data persists across restarts (SQLite is fine).
- Errors are reported clearly; no silent failures on issue/return.
- Code is small, readable and covered by at least a handful of tests.
