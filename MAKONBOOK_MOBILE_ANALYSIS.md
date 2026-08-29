# MakonBook — Technical Audit for Mobile App & New Backend Design

**Audit date:** 2026-08-16
**Scope:** Full read of the MakonBook Django codebase (backend + server-rendered frontend), performed to serve as the single source of truth for designing a new, separate STUDENT-ONLY mobile app and its own new backend. Admin/teacher web functionality is documented only as deep as needed to understand the content pipeline.
**Method:** Every finding below is traceable to a file path (and usually a line number). Where the code was ambiguous or a design intent could not be confirmed from source, it is listed in [Section 10 — Open Questions](#10-open-questions) instead of being assumed.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack Summary](#2-tech-stack-summary)
3. [Architecture Overview](#3-architecture-overview)
4. [Backend Deep-Dive](#4-backend-deep-dive)
   - 4.1 [Student-Facing API/Endpoint Map](#41-student-facing-apiendpoint-map)
   - 4.2 [Admin/Teacher-Only Endpoints (brief)](#42-adminteacher-only-endpoints-brief)
   - 4.3 [Authentication & Authorization](#43-authentication--authorization)
   - 4.4 [Database Schema](#44-database-schema)
   - 4.5 [Core Business Logic](#45-core-business-logic)
   - 4.6 [Third-Party Integrations](#46-third-party-integrations)
   - 4.7 [Security Measures](#47-security-measures)
   - 4.8 [Caching](#48-caching)
5. [Frontend Deep-Dive](#5-frontend-deep-dive)
6. [Data Models Reference](#6-data-models-reference)
7. [User Roles & Permissions](#7-user-roles--permissions)
8. [Non-Functional Notes](#8-non-functional-notes)
9. [Recommendations for the Mobile App](#9-recommendations-for-the-mobile-app)
10. [Open Questions](#10-open-questions)

---

## 1. Project Overview

MakonBook is a Django 5.1.5 web platform for **"SAT Makon"**, a learning center that prepares students for the SAT and (secondarily) AP exams. It is one server-rendered monolith — there is no separate JS single-page app and no existing mobile app.

### Who uses it
- **Students** — take full-length practice SAT tests (English + Math, 2 modules each), study vocabulary, set score goals, browse college-admissions guidance, book 1:1 support lessons with a tutor, optionally join a **classroom** run by a teacher, and (without any account at all) can take public **guest "global event"** mock exams or AP practice exams.
- **Teachers** — own one or more `Classroom`s, approve/reject student join requests, control which content sections (practice tests / vocabulary / admissions) a classroom can see, manage vocabulary content, chat with their class, view per-student progress, and give 1–5 star + written assessments (`apps.ratings`).
- **Support Teachers** — a distinct role: tutors with a public bookable profile, weekly availability windows, and a request→group-session booking workflow.
- **Admins / Managers / Testers** — Django-`Group`-based elevated roles for content management (creating/editing questions, assigning tests to groups, generating bulk "Mock" exam sessions with throwaway accounts), user/group administration, and (Manager) an operational dashboard over teachers/classrooms.
- **Telegram-bot admins** — a completely separate identity system (not Django `User`), used only by internal staff to bulk-generate student accounts via a Telegram chat bot.

**Mobile app scope, per the brief driving this audit: STUDENTS ONLY.** Everything under "Teachers", "Admins/Managers/Testers", and the Telegram bot is web-only and out of scope for the mobile app itself — but the *admin content pipeline* (how Tests/Questions get created and how a student becomes entitled to see them) is documented in [4.5](#45-core-business-logic) and [9](#9-recommendations-for-the-mobile-app) because mobile content has to originate from that same pipeline.

### High-level student journey
1. **Register** (username + email + password, or Google OAuth) → account is **auto-activated immediately** (email verification is present in the schema but currently disabled in the live registration code path — see [4.3](#43-authentication--authorization)).
2. **Land on `/sat/`** (`classroom_entry`) → if not in any classroom, see a simple "join a classroom" screen plus a global student-goal dashboard; if in an approved classroom, land on classroom-scoped views instead.
3. **Optionally join a classroom** via a teacher-issued 6-digit code → request goes `pending` until the teacher approves it; approval seeds per-section access flags from the classroom's policy.
4. **Browse practice tests** (`/sat/practice_tests/`) — a dashboard of `Test` objects the student is entitled to see (via Django-group membership for non-classroom students, or via classroom-scoped `StudentPracticeTestAccess` for classroom students), each annotated with progress state (start / continue / finalizing / done).
5. **Start a test** → answer Module 1 English → Module 2 English → Module 1 Math → Module 2 Math, each under an independent, **server-authoritative countdown timer** (32 min English / 35 min Math by default) with autosave every ~20s and instant resume from any device/refresh.
6. **View results** — a scaled 400–1600 score computed from a hand-built curve formula (not a real College Board lookup table — see [4.5](#45-core-business-logic)), with per-question correct/incorrect review and a downloadable PDF certificate.
7. **Review answers/explanations** for any past attempt (governed by a role-based review-time-window policy).
8. Secondary features along the way: **Vocabulary** (unit-based flashcards + quizzes with a simple mastery tracker), **Student Goals** (target score / dream university dashboard), **Support-Teacher booking** (request a topic, get grouped into a teacher-scheduled session), **Admissions** (static, non-editable guidance content), **Classroom chat** (poll-based), and (if not in a classroom / anonymous) **Guest global events** — timed public mock exams taken with no account at all.

---

## 2. Tech Stack Summary

| Layer | Technology | Notes |
|---|---|---|
| Backend framework | **Django 5.1.5** (Python, `requirements.txt`; project docs say Python 3.12.3) | Classic server-rendered MVT app, no DRF/GraphQL |
| Package manager (Python) | `pip` + `requirements.txt` (44 lines) | No poetry/pipenv |
| Database | **PostgreSQL 16.9** in production (migrated from SQLite in July 2025, `docs/postgresql_migration_guide.md`); SQLite remains the local-dev fallback in `satmakon/settings.py` | ORM: Django's built-in ORM (no separate query layer) |
| Frontend | **Django Templates** (server-rendered HTML) + vanilla JS/jQuery + **two coexisting Bootstrap versions** (4.3.1 for the app, 5.3.3 vendored with a landing-page theme) | **No React/Vue/Angular, no `package.json`, no JS package manager** — confirmed absent from the repo |
| Frontend build tooling | None — static assets are hand-written and served via **WhiteNoise** (`CompressedManifestStaticFilesStorage`) | No webpack/vite/esbuild |
| Auth | Django session cookies + CSRF cookie (custom name `makonbook_csrftoken_v35`) + **django-allauth** for Google OAuth | **No JWT/token/DRF auth layer exists anywhere in the codebase** (confirmed by repo-wide grep) |
| Object/file storage | **Cloudflare R2** (S3-compatible) via `django-storages` + `boto3`, split into a public bucket path (`PublicStorage`, unsigned URLs) and a private path (`PrivateStorage`, signed URLs) | Static files are *not* on R2 (WhiteNoise/local); only media (question images, videos, certificates) |
| PDF generation | **PyMuPDF (`fitz`)** | Used for SAT score certificates and for an internal AI question-audit report |
| Email | SMTP (`django.core.mail`, configurable host, defaults to `smtp.gmail.com`) | Used for password-reset codes only; registration email verification is currently bypassed |
| Background/async jobs | **None functional.** `apps/sat/tasks.py` imports Celery, but Celery/Redis are not installed, not configured, and the task is never called anywhere — dead code | No cron, no APScheduler, no django-q |
| Messaging bot | **aiogram 3.13.1** (async Telegram bot), admin-only tool to bulk-create student accounts, run in its own Docker container | Not student-facing |
| Hosting/deployment | **Docker Compose** (`docker-compose.yml` dev, `docker-compose.prod.yml` prod) — `web` (gunicorn), `telegram-bot`, `nginx` (reverse proxy + TLS), `db` (Postgres, dev only — prod shares an external Postgres container) | `certbot` container handles Let's Encrypt renewal in prod |
| WSGI server | **gunicorn** | `satmakon.wsgi.application` |
| CI | None found in the repo (no `.github/workflows`, no CI config) | |

---

## 3. Architecture Overview

### Repo structure — single Django monorepo, no separate frontend/backend split

```
makonbook-sat-main/
├── apps/
│   ├── base/          # Auth, registration, password reset, user profile, issue reports
│   ├── sat/            # Core: SAT tests, questions, scoring, classrooms, vocabulary,
│   │                    # student goals, support-teacher booking, guest/global events
│   ├── apclasses/      # AP exam feature (parallel exam engine, MCQ + FRQ, guest-capable)
│   ├── ratings/        # Teacher-given student assessments + public rating board + parent lookup
│   └── telegram_bot/   # Internal admin bot (aiogram) — bulk user creation, NOT student-facing
├── satmakon/           # Django project: settings.py, urls.py, wsgi.py
├── templates/          # All server-rendered HTML (grouped by app/feature)
├── static/              # Hand-written CSS/JS + vendored libraries (source)
├── staticfiles/        # `collectstatic` output (generated, not source)
├── media/               # Local media fallback (prod media actually lives on R2)
├── nginx/, scripts/nginx/  # Reverse proxy configs (dev + prod)
├── docker-compose.yml, docker-compose.prod.yml, Dockerfile, entrypoint.sh
└── docs/                # Historical/operational docs (see Non-Functional Notes)
```

There is **no API layer distinct from the website** — the "backend" and "frontend" are the same Django process; templates are rendered server-side and interactive pieces (autosave, chat, quizzes) call back into ordinary Django views that return JSON when the request is AJAX (`X-Requested-With: XMLHttpRequest`) and HTML otherwise. **This means a new mobile backend cannot simply "point the app at the existing API" — no JSON API contract currently exists to build on; new endpoints would need to be designed from scratch**, even if the underlying business logic (scoring, timers, access control) is reused.

### Frontend ↔ backend communication
- Classic full-page navigation for most flows (Django `render()` + template).
- AJAX/`fetch()` JSON endpoints for: exam autosave (`save_test_module_draft`), module submission (`check_the_answers`), classroom chat send/fetch, vocabulary flashcard marking, student-goal saving, CSRF-token refresh, guest exam autosave/submit.
- **No API versioning** — URLs are plain Django `path()` routes under `/sat/`, `/`, `/rating/`, `/ap-classes/`, `/admin/`.
- **No WebSockets/SSE anywhere.** "Real-time" features are short-poll: classroom chat polls every 3s (visible tab) / 15s (hidden tab); classroom-join-status page polls via a full page reload every ≥3–5s.

### Background processes / workers / cron
- **None are functional in production.** The only `celery`-decorated task (`convert_video_to_hls` in `apps/sat/tasks.py`) cannot even run — Celery isn't in `requirements.txt`, there's no Redis/broker, and no code anywhere calls the function. This is a vestige of an unfinished HLS video-streaming feature.
- The only genuinely scheduled process in the whole stack is infrastructure-level: the `certbot` container's TLS-renewal loop (every 12h) in `docker-compose.prod.yml`.
- Two content-audit tools exist as **manual CLI management commands** only (not scheduled, not web-triggered): a heuristic data-integrity checker (`audit_data_integrity[_v2].py`) and an OpenAI-backed question-quality auditor (`audit_questions_with_ai.py`).

### Microservices
None. The only separate *deployable unit* sharing the same codebase/database is the Telegram bot container (`telegram-bot` service in Compose) — an admin tool, not a service boundary in the architectural sense.

---

## 4. Backend Deep-Dive

### 4.1 Student-Facing API/Endpoint Map

All routes are session-cookie-authenticated Django views (`@login_required` unless noted). Base URL prefixes: `apps/base` → `/`, `apps/sat` → `/sat/`, `apps/ratings` → `/rating/`, `apps/apclasses` → `/ap-classes/`. Source: `apps/base/urls.py`, `apps/sat/urls.py`, `apps/ratings/urls.py`, `apps/apclasses/urls.py`, cross-referenced against view bodies in `apps/base/views.py`, `apps/sat/views.py`, `apps/sat/guest_views.py`, `apps/apclasses/views.py`.

#### Auth & account (`apps/base`)

| Method | Path | View | Purpose | Auth |
|---|---|---|---|---|
| GET/POST | `/login/` | `loginUser` | Username-or-email + password login; redirects authenticated users away | Anonymous only |
| GET/POST | `/register/` | `register` | Create account; auto-activates immediately (see 4.3) | Anonymous |
| GET | `/logout/` | `logoutUser` | Session logout | Any |
| GET/POST | `/forgot-password/` | `forgot_password` | Request a 6-digit email reset code | Anonymous |
| GET/POST | `/reset-password/` | `password_reset_confirm` | Submit code + new password | Anonymous |
| GET | `/activate/<uuid:token>/` | `activate` | Legacy email-verification link (not used by live registration flow) | Anonymous |
| GET/POST | `/edit-profile/` | `edit_profile` | Edit profile (offline-group users can set custom section timers) | Login required |
| POST | `/complete-profile-name/` | `complete_profile_name` | AJAX: set first/last name (soft prompt, not confirmed as a hard gate — see Open Questions) | Login required |
| POST | `/report-issue/` | `submit_general_issue_report` | Submit a bug/content/account report | Any |
| GET/POST | `/accounts/...` | django-allauth | Google OAuth login/callback | Anonymous |

#### Core exam-taking (`apps/sat`)

| Method | Path | View | Purpose | Auth |
|---|---|---|---|---|
| GET | `/sat/` | `classroom_entry` (`sat_menu`) | Landing/router: routes teachers/managers/support-teachers to their dashboards, else shows classroom status + goal dashboard | Login required (no explicit `@login_required`, see Open Questions) |
| GET | `/sat/practice_tests/` | `practice_tests` | Dashboard of tests the student is entitled to, with progress state | Login required |
| GET | `/sat/practise/<pk>` | `start_Practise` (`practise`) | Start/resume a test attempt; auto-redirects into the resumable module if one exists | Login + `user_has_test_access` |
| GET | `/sat/practise/<pk>/start` | `module_test` (`test`) | The actual module-taking page (timer, questions, autosave state) | Login + test access |
| POST | `/sat/test-flow/draft/save/` | `save_test_module_draft` | **Autosave** endpoint (partial answers, ~every 20s + on key events) | Login + test/classroom access |
| POST | `/sat/check_the_answers` | `check_the_answers` | **Module submission** (must be complete); also (staff/tester only) legacy single-answer-check | Login + test access |
| GET | `/sat/restart/<pk>` (POST) | `restart` | Restart a full test attempt (new `attempt_id`, unlimited retakes) | Login + test access |
| POST | `/sat/restart_section/<pk>/<section>/` | `restart_section` | Restart just one section, preserving the other section's saved modules | Login + test access |
| GET | `/sat/results/<test>` | `results` | Score + section/module breakdown for the current or a past attempt | Login |
| GET | `/sat/results/certificate/<test>/` | `certificate` | Generate/serve the PDF certificate | Login |
| GET | `/sat/rankings/<pk>` | `rankings` | **Top-50 leaderboard for a test — no auth, no classroom scoping** (flag) | **None** |
| GET | `/sat/question/<key>/<section>/<module>/<id>` | `question` | Post-hoc review of one question with explanation | Login (owner or Admin) |
| GET | `/sat/start-makeup-test/<pk>/` | `start_makeup_test` | Start/resume a teacher-curated "makeup" test | Login |
| GET | `/sat/makeup-test-module/<pk>/` | `makeup_test_module` | Module-taking page for makeup tests | Login |
| GET/POST | `/sat/enter-code/` | `enter_secret_code` | Redeem a 6-digit secret code for group/test access | Login |
| GET/POST | `/sat/punishment/<pk>` | `punishment` | Logs a `Punishment` row — **dead code, nothing calls it client-side** | Login |

#### Classroom (student side)

| Method | Path | View | Purpose |
|---|---|---|---|
| POST | `/sat/join/` | `submit_classroom_join_request` | Submit a 6-digit join code (rate-limited) |
| GET | `/sat/join/status/` | `classroom_join_status` | View pending/approved/rejected classroom memberships |
| GET | `/sat/classroom/<id>/` | `student_classroom_home` | Classroom-scoped student home |
| POST | `/sat/classroom/<id>/leave/` | `leave_classroom` | Leave a classroom |
| GET | `/sat/classroom/<id>/practice-tests/` | `classroom_practice_tests` | Classroom-scoped test dashboard |
| GET | `/sat/classroom/<id>/practice/<pk>/start/` | `classroom_start_practise` | Classroom-scoped test start |
| GET | `/sat/classroom/<id>/practice/<pk>/module/` | `classroom_module_test` | Classroom-scoped module-taking |
| GET | `/sat/classroom/<id>/vocabulary/…` | `classroom_vocabulary*` | Classroom-scoped vocabulary (same engine as global, scoped progress) |
| GET | `/sat/classroom/<id>/admissions/` | `classroom_admissions` | Classroom-scoped admissions content |
| GET | `/sat/classroom/<id>/ap-tests/` | `classroom_ap_tests` | AP events linked to an AP-type classroom |
| GET | `/sat/classroom/<id>/chat/` | `classroom_chat` | Chat page |
| POST/GET | `/sat/classroom/<id>/chat/send/`, `/fetch/` | `send_classroom_message`, `fetch_classroom_messages` | Send message / **poll for new messages** (`?last_id=`) |

#### Vocabulary, admissions, goals (global, non-classroom)

| Method | Path | View | Purpose |
|---|---|---|---|
| GET | `/sat/vocabulary/` | `vocabulary` | Unit list + progress |
| GET | `/sat/vocabulary/<slug>/` | `vocabulary_section` | Word list or flashcards view |
| POST | `/sat/vocabulary/flashcards/mark/` | `vocabulary_flashcard_mark` | AJAX: mark a flashcard `again`/`learning`/`known` |
| GET/POST | `/sat/vocabulary/practice-quiz/…` | `vocabulary_practice_quiz*` | Quiz setup → start → result (session-based until submit) |
| GET | `/sat/admissions/`, `/sat/admissions/<slug>/` | `admissions*` | **Static, hardcoded content** — not admin-editable |
| GET | `/sat/student/goals/` | `student_goal_settings` | GET redirects to dashboard; POST (form or AJAX) saves goal |
| GET | `/sat/student/goals/csrf/` | `student_goal_csrf` | Refresh CSRF token for the goal-save AJAX flow |

#### Support-teacher booking (student side)

| Method | Path | View | Purpose |
|---|---|---|---|
| GET | `/sat/support-teachers/` | `support_teacher_list` | Directory + search/filter |
| GET | `/sat/support-teachers/<id>/` | `support_teacher_detail` | Profile, topics, availability |
| POST | `/sat/support-teachers/<id>/book/` | `book_support_lesson` | Request a topic (auto-joins an open group session if one exists, else queues a request) |
| GET | `/sat/support-lessons/` | `my_support_lessons` | Waiting / upcoming / history bookings |
| POST | `/sat/support-lessons/<id>/cancel/` | `cancel_support_lesson` | Cancel (subject to notice-window rule) |
| POST | `/sat/support-lessons/<id>/feedback/` | `leave_support_lesson_feedback` | 1–5 star + text, **private** (never shown publicly) |

#### Guest / no-login exam flow (`apps/sat/guest_views.py`, prefix `/sat/`)

| Method | Path | View | Purpose |
|---|---|---|---|
| GET/POST | `/sat/guest/` | `guest_entry_view` | Create a `GuestParticipant` + Django session (no password) |
| GET | `/sat/global-events/` | `global_event_list_view` | Public list of live/upcoming guest exam events |
| GET | `/sat/global-events/<slug>/` | `global_event_detail_view` | Event detail |
| POST | `/sat/global-events/<slug>/start/` | `start_global_event_view` | Start/resume an attempt (access-code check, rate-limited) |
| GET/POST | `/sat/global-events/attempt/<token>/`, `/save/`, `/submit/` | guest attempt views | Same timer/autosave/submit pattern as the logged-in flow, scoped by `guest_token` + session |
| GET | `.../result/`, `.../review/` | guest result/review views | Score + review (gated by event settings) |
| GET | `/sat/global-events/<slug>/leaderboard/` | `global_event_leaderboard_view` | Top-100, **names masked** |

#### AP Classes (`apps/apclasses`, prefix `/ap-classes/`)

| Method | Path | View | Purpose |
|---|---|---|---|
| GET | `/ap-classes/` | `ap_event_list_view` | List visible AP exam events |
| GET | `/ap-classes/events/<slug>/` | `ap_event_detail_view` | Detail + secret-code unlock |
| POST | `/ap-classes/events/<slug>/start/` | `start_ap_event_view` | Start/resume attempt (logged-in **or** guest) |
| GET/POST | `/ap-classes/attempt/<token>/` | `ap_attempt_view` | Part A (MCQ, no calc) → Part B (MCQ, Desmos) → FRQ, one view for all three |
| POST | `/ap-classes/attempt/<token>/frq-upload/` | `upload_frq_submission_view` | Upload a photographed handwritten FRQ page |
| POST | `/ap-classes/attempt/<token>/submit/` | `submit_ap_attempt_view` | Manual submit |
| GET | `/ap-classes/attempt/<token>/result/`, `/review/<qid>/` | result/review views | Score (MCQ auto-graded only) + per-question review |

#### Ratings (`apps/ratings`, prefix `/rating/`)

| Method | Path | View | Purpose |
|---|---|---|---|
| GET | `/rating/` | `rating_home` | Public rating board (top-N students, if enabled) |
| GET | `/rating/student/<id>/` | `public_student` | Public profile card |
| GET | `/rating/parent/` | `parent_lookup` | Parent-facing lookup by access code — **the only page in the whole app with real i18n (EN/RU/UZ)** |

### 4.2 Admin/Teacher-Only Endpoints (brief)

Not deep-dived per the audit brief — listed for completeness only. All under `/sat/admin-panel/` (custom staff panel, **not** Django's `/admin/`) unless noted.

- **Users/Groups**: `admin_users`, `admin_user_detail/edit/delete/create`, `admin_groups`, `admin_group_detail/delete/remove_user`, `edit_group_tests` (assign `Test`s to a `Group` — the core group-based access-control mechanism).
- **Tests/Mocks**: `admin_tests`, `admin_test_detail` (read-only dashboards — question creation itself happens through Django's built-in `/admin/` interface), `admin_mocks`, `admin_mock_create/detail/download/delete` (bulk-provisions a `Group` + throwaway `User` accounts + a `Mock` bundle for one proctored session; `admin_mock_download` streams **plaintext** generated passwords as a `.txt` file — flagged as a real security concern in [8](#8-non-functional-notes)).
- **Support teachers (admin side)**: `admin_support_teachers`, `admin_support_bookings`, teacher create/edit/toggle/availability CRUD.
- **Classroom/teacher management**: `teacher_classroom_list/dashboard`, `create_classroom`, `generate_classroom_join_code`, `classroom_join_requests`, `approve_join_request`/`reject_join_request`, `update_student_section_access`, `update_classroom_section_access`, `update_classroom_practice_test_access`, `update_classroom_ap_test_access`, `classroom_progress_dashboard` and its per-student/per-section drill-downs, `delete_classroom`, `edit_classroom`.
- **Vocabulary (teacher content management)**: `teacher_vocabulary_units`, `create_vocabulary_unit/word/question`, `bulk_import_vocabulary_words`.
- **Manager role**: `manager_dashboard`, `manager_teacher_detail`, `manager_classroom_detail`.
- **Support-teacher self-service**: `support_teacher_profile_edit`, availability add/delete, `support_teacher_planner`, `schedule_support_topic_session`, `manage_support_session`, `manage_support_lesson`.
- **Ratings (teacher side)**: `teacher_classroom_ratings`, `assess_student`, `edit_assessment`.
- **AP Classes (admin)**: exam/question/FRQ CRUD under `apps/apclasses/urls.py` app-internal admin templates (not enumerated here).
- **Dev tools**: everything under `/sat/dev/` (gated to the `dev` group) — internal QA/debugging utilities, out of scope.

### 4.3 Authentication & Authorization

**Mechanism: 100% classic Django session-cookie auth. There is no JWT/token/API-key layer anywhere in this codebase** (confirmed by repo-wide grep for `rest_framework`, `JWT`, `TokenAuthentication`, `Authorization: Bearer` — the only Bearer-token usage in the entire repo is the server calling *out* to OpenAI for the question-audit tool, unrelated to user auth).

- **Session/CSRF**: `SESSION_COOKIE_SAMESITE=Lax`, custom CSRF cookie name `makonbook_csrftoken_v35` (`satmakon/settings.py:292`, deliberately versioned to avoid stale-cookie collisions across domain aliases), `CSRF_COOKIE_SAMESITE=Lax`, both cookies `Secure` in production.
- **`AUTHENTICATION_BACKENDS`**: Django's `ModelBackend` + allauth's backend (`satmakon/settings.py:387-390`).

**Registration** (`apps/base/views.py:154-200`, form `apps/base/forms.py:9-61`): username + email (both case-insensitive-unique) + password (validated by Django's standard password validators). **Email verification is effectively disabled in the live code path** — on success the view immediately does:
```python
user.is_active = True
user.save(update_fields=["is_active"])
EmailVerification.objects.update_or_create(
    user=user,
    defaults={"is_verified": True, "expires_at": timezone.now() + timedelta(days=3650)},
)
```
(`apps/base/views.py:169-178`) — no verification email is actually sent, though the `EmailVerification` model, its 24-hour-expiry default, and the `/activate/<token>/` view all still exist unused. **Decide explicitly whether the mobile signup flow should (re-)implement real verification.**

**Login** (`apps/base/views.py:125-147`): accepts username *or* email (an `@` in the field triggers an email lookup, then authenticates by the resolved username). Generic error message on failure (no username enumeration). **No rate-limiting or lockout on failed login attempts** — a real gap to close in the new backend, especially since password-reset and classroom-join-code flows *do* rate-limit elsewhere.

**Google OAuth**: fully delegated to `django-allauth` (`satmakon/settings.py:398-424`) — `SOCIALACCOUNT_EMAIL_VERIFICATION="none"`, PKCE enabled, auto-connects Google sign-in to an existing email/password account by verified email. No custom adapter code was found. A mobile app would very likely use native Google Sign-In (ID-token verification server-side) rather than reuse allauth's redirect flow.

**Password reset** (`apps/base/views.py:204-326`): 6-digit numeric code, **hashed** (`make_password`) before storage, 10-minute expiry, **5-attempt limit** (auto-invalidated past that), sent by email only (no SMS). Always returns a generic success message regardless of whether the email exists (anti-enumeration).

**Profile-completion gate** (`complete_profile_name`, `apps/base/views.py:86-116`): AJAX endpoint validating first/last name (Unicode-aware — accepts Uzbek/Russian characters, hyphens, apostrophes). **Could not confirm from `views.py` alone whether this is a hard onboarding gate or a soft, dismissible prompt** — see Open Questions.

**Roles are Django `Group` rows**, not a `role` field on `User`. Exact group name strings found in code (`apps/sat/views.py`, `apps/base/models.py`, grep for `.groups.filter(name=`):

| Group | Grants |
|---|---|
| `OFFLINE` | Per-user custom English/Math section time limits (`UserProfile.english_time_minutes`/`math_time_minutes`); also a longer review window / more retakes per `docs/review_time_policy.md` (3 days / 4 retakes vs. 24h / 2 retakes for regular students) |
| `Admin`, `Tester` | Elevated bypass rights inside `apps/sat` (classroom-teacher-only checks, review-ownership checks, single-answer-check endpoint) |
| `Manager` | Routes to a manager dashboard (`is_manager()`); operational oversight of teachers/classrooms |
| `teacher` (case-insensitive) | `is_teacher()` = has the group **or** owns an active `Classroom` row (classroom ownership alone is treated as authoritative even without the group, for legacy accounts) |
| `student` | Loose/fallback definition — essentially "not a teacher" |
| `dev` | Internal dev-tools access |
| `Support Teacher` (implied by having a `SupportTeacherProfile` row, not strictly a group) | Routes to the support-teacher planner |

`is_staff`/`is_superuser` (Django's built-ins) are checked **independently** and treated as always-elevated in most gates — there isn't one single "is this person staff" check; both mechanisms coexist. The generic `allowed_users(allowed=[])` decorator (`apps/base/decorators.py:12-22`) rejects with a plain-text 200 response (not a real HTTP 403) if the user lacks any listed group — a mobile API should use real status codes instead.

**Guest identity** (no account at all): a `GuestParticipant` row (UUID, name, session key — no password) created via `guest_entry_view`, tracked purely through the Django **session cookie** (`request.session["guest_id"]`). Per-attempt URLs also embed a `guest_token` UUID, but every view that receives it still cross-checks it against the session-derived guest — so the token alone isn't a bearer credential. **Guest attempts are never linked to a real account after registration — there is no merge/conversion path anywhere in the code.** This is a genuine product decision needed before mobile "try before you sign up" can work.

**Classroom membership**: join-code (6-digit, teacher-generated, 12h expiry) → student submits it (IP-rate-limited: 5 attempts / 10 min) → membership created `pending` → teacher approves/rejects. Approval seeds per-section access flags (`StudentSectionAccess`) from the classroom's saved policy (`apps/sat/classroom_access_policy.py`) and, if practice tests are enabled, materializes which specific `Test`s the student can see (`ClassroomPracticeTestAccessPolicy`: all tests, or a hand-picked subset).

**Two parallel test-access systems coexist** (flagged as a design point to resolve for the mobile backend): (1) global `Test.groups` M2M — a legacy/non-classroom student sees a test if they share a Django group with it; (2) classroom-scoped `StudentPracticeTestAccess`, materialized per the policy above. `user_has_test_access()` (`apps/sat/views.py:912`) checks both depending on whether the requesting user is classroom-bound.

### 4.4 Database Schema

Full field-by-field detail (with file:line citations) is preserved for engineering reference in [Section 6](#6-data-models-reference). Below is the orientation map of every model relevant to students and exam content.

**Structural caveats to design around** in a new schema:
1. `Test.name` is the **primary key** (a string, e.g. `"12"`), not an auto-increment id — every FK to `Test` stores a string.
2. Two different "module" vocabularies coexist: the question bank uses `module_1`/`module_2`; attempt-tracking (`TestModule`, drafts) uses `m1`/`m2` — reconciled ad hoc in code (`f'module_{module[1]}'`). Pick one convention for the new schema.
3. No adaptive-difficulty branching exists anywhere in the models — Module 2 content is static per test, not selected based on Module 1 performance (see [4.5](#45-core-business-logic)).
4. The autosave/draft pattern (`answers`, `time_spent`, `eliminated_choices`, `marked_for_review`, `current_question_index`, `deadline_at`) is duplicated near-identically three times (`TestModuleDraft`, `MakeupTestModuleDraft`, `GlobalEventModuleDraft`) — a good candidate to unify into one generic draft table in the new backend.
5. `GlobalEventAnswer.question_id` is a raw integer with **no FK/referential integrity** (disambiguated only by a `section` string) — contrast with the AP app's `APExamAnswer.question`, which is a proper FK. Normalize this in the new schema.
6. **No payment/subscription model exists anywhere.** The only "purchase"-named model (`PurchasedLessonPackage`) has no price/currency/transaction fields — it's a manually-granted entitlement flag, not real payment infrastructure.
7. `BaseVideo` (HLS video model) and `Lesson.videos`/`LessonProgress.check_completion()` are **broken/dead code** — `check_completion()` references a `lesson.videos` relation that doesn't actually exist and would raise `AttributeError` if called. Do not port as-is.

#### Model inventory by app

**`apps.base`** — `EmailVerification`, `PasswordResetCode`, `UserProfile` (1:1 with `User`, per-section timers), `GeneralIssueReport`.

**`apps.sat`** (core, 51 models) — grouped:
- *Question bank*: `QuestionDomain`, `QuestionType`, `Test`, `English_Question`, `Math_Question`, `MakeupTest` (+ its through-tables), `SecretCode`, `Mock`.
- *Attempt/scoring engine*: `TestModule`, `TestModuleDraft`, `MakeupTestModuleDraft`, `TestReview`, `TestStage`, `Punishment` (see anti-cheat note below).
- *Classroom system*: `Classroom`, `ClassroomJoinCode`, `ClassroomMembership`, `StudentSectionAccess`, `ClassroomSectionAccessPolicy`, `ClassroomPracticeTestAccessPolicy`, `StudentPracticeTestAccess`, `StudentProgress`, `ChatMessage`.
- *Guest/global events*: `GlobalEvent`, `GuestParticipant`, `GlobalEventAttempt`, `GlobalEventModuleDraft`, `GlobalEventAnswer`.
- *Vocabulary*: `VocabularyUnit`, `VocabularyWord`, `VocabularyQuestion`, `VocabularyWordProgress`, `VocabularyQuizAttempt`, `VocabularyQuizAnswer`.
- *Student goals*: `DreamUniversity`, `StudentGoalProfile`.
- *Support-teacher booking*: `SupportTeacherProfile`, `SupportTeacherAvailability`, `SupportLessonTitle`, `SupportLessonTopic`, `SupportLessonSession`, `SupportLessonBooking`, `SupportTeacherReview`.
- *Lessons (mostly unused/broken feature)*: `LessonPackage`, `Lesson`, `LessonProgress`, `PurchasedLessonPackage`, `BaseVideo`.

**`apps.apclasses`** — `APClass`, `APMockExam`, `APMultipleChoiceQuestion` (5 choices, unlike SAT's 4), `APFRQPage`, `APExamEvent`, `APExamAttempt` (supports both `User` and guest in one table), `APExamAnswer`, `APFRQSubmission` (human-graded).

**`apps.ratings`** — `RatingConfig` (singleton, EWMA rating parameters), `RatingProfile` (1:1 with `User`, parent access code), `RatingAssessment` (5 sub-scores given by a teacher, cross-app FK into `sat.Classroom`).

**`apps.telegram_bot`** — `TelegramAdmin` (independent identity, not linked to `User`), `BulkUserRequest`, `GeneratedUser` (stores a raw/unhashed temporary password field — flagged as a credential-handling anti-pattern in [8](#8-non-functional-notes)).

### 4.5 Core Business Logic

#### How mock exams are structured & assigned

A `Test` is a minimal shell (`name` = primary key string, `groups` M2M for access, an `icon`). Content is attached at the question level: `English_Question`/`Math_Question` rows each carry `test` (FK), `module` (`module_1`/`module_2`), `number` (order within module), `domain`/`type` (taxonomy FKs), and the section (English vs. Math) is determined by **which table the row lives in**, not a field. There is no separate `Module`/`Section` model — "module" is purely a grouping tag on question rows plus a runtime sequence (`get_test_sequence()`) built from whichever modules actually have questions.

There is a second, parallel content type: **`MakeupTest`** — a teacher-curated bundle of hand-picked questions (via an ordered through-table) from the same question pools, used for retake/alternate sessions, independent of the numbered `Test` catalog.

**Access control**: a `Test` is visible to a non-classroom student only if they share a Django `Group` with `Test.groups` (assigned via the admin's `edit_group_tests` screen — a full replace-set operation, not additive). Classroom students instead see whatever `StudentPracticeTestAccess` rows their membership has (seeded from the classroom's policy). **These two systems are independent and not obviously reconciled** — worth explicit design attention for the new backend's authorization model.

**Content creation pipeline (admin/teacher side, web-only)**: Questions are created **one at a time** through Django's built-in `/admin/` interface (custom forms with a "Save and go to next question" convenience button implying sequential manual entry) — **there is no bulk CSV/JSON import UI**. A few one-off developer CLI scripts exist (`apps/sat/management/commands/copy_english_questions.py` etc.) for DB-to-DB copies, not for external import. **Implication for the mobile backend: there is no existing structured export/import format to reuse — a new content-sync mechanism has to be designed from scratch** (see [9](#9-recommendations-for-the-mobile-app)).

A related but distinct concept, **`Mock`**, is an operational bundle (Test + auto-created Group + batch of throwaway `User` accounts with generated credentials) used to run one proctored mock-exam session — not exam content itself.

An **AI-assisted content-quality audit** exists (`apps/sat/question_audit.py`) — a CLI-only management command that sends question text (never student data) to OpenAI (`gpt-5.6-terra` per settings default) to independently re-solve every question and flag `wrong_key`/`ambiguous`/`multiple_valid_answers`/etc., producing a PDF report. It is explicitly read-only (no DB writes) and not wired into any web UI or scheduled job.

#### Timing/timer logic

**Fully server-authoritative, with zero session-state dependency** — a major finding relevant to mobile design. Timer state lives entirely in the DB (`TestModuleDraft.deadline_at`), keyed by `(user, test, attempt_id, section, module)`:

- The deadline is **set once**, the instant a module page is first opened (`GET`), and is **never extended** by activity — `_ensure_regular_module_draft()` only backfills a missing deadline, never overwrites an existing one (`apps/sat/views.py:672`).
- Default durations: **English = 1920s (32 min), Math = 2100s (35 min)** (`_module_duration_seconds`, `apps/sat/views.py:448`), overridable per-student only for the `OFFLINE` accommodation group via `UserProfile`.
- Every autosave request re-checks the server clock against `deadline_at`; if expired, the client-submitted answers are **discarded** and replaced with the last-known-good server draft (`apps/sat/views.py:2156`, comment: *"The deadline is server-authoritative. A forged or delayed request may not change answers after time expires."*).
- If a student never explicitly submits, simply **loading the module page again** after the deadline auto-submits it from the draft (`_regular_module_runtime`, `apps/sat/views.py:761`).
- Client-side, `sat-test-core-v13.js` renders the countdown as `deadlineAt (server epoch) − Date.now()` on a 500ms interval — not a locally-decremented counter — so device sleep/backgrounding can't drift it, and every autosave response can resync `deadlineAt`.

**Mobile-design implication**: this architecture is *good news* — timer correctness doesn't depend on the client, so a mobile client just needs to render `deadline_at` and periodically sync. The risk is the **no-grace-period** behavior: if a mobile device loses connectivity or is backgrounded for the module's full duration, the next request (even just reopening the app) force-submits whatever was last saved — there's no "time paused while offline" concept today. This needs a deliberate decision for mobile (see [9](#9-recommendations-for-the-mobile-app)).

#### Autosave

Client → `POST /sat/test-flow/draft/save/` (`apps/sat/views.py:1741`), triggered by: every answer change (900ms debounce), navigation (1300ms debounce), a 20-second background interval, `visibilitychange`→hidden, and `beforeunload`. The endpoint accepts **partial** answer sets (unlike final submission, which requires every question answered), row-locks the `TestStage` to detect stale tabs/old attempts (`409` if `attempt_id` mismatches), and returns the authoritative `remaining_seconds`/`deadline_at` on every response. The client also mirrors state to `localStorage` and merges (timestamp-based "latest wins") with whatever the server returns on load — providing resilience to a full offline session, though not true queued-offline-writes.

#### Scoring algorithm — quoted in full

**Not a real College Board lookup table.** It's a self-contained, hand-tuned Python formula in `apps/sat/libs/calculator.py`:

```python
# apps/sat/libs/calculator.py:3-47
DEFAULT_BANDS = [
    {"name": "low",  "min_ratio": 0.00, "max_ratio": 0.449999, "m2_weight": 0.36, "m2_multiplier": 0.92, "section_cap": 650, "curve_power": 1.02, "range_half": 20},
    {"name": "mid",  "min_ratio": 0.45, "max_ratio": 0.749999, "m2_weight": 0.42, "m2_multiplier": 1.00, "section_cap": 730, "curve_power": 0.97, "range_half": 20},
    {"name": "high", "min_ratio": 0.75, "max_ratio": 1.00,     "m2_weight": 0.48, "m2_multiplier": 1.05, "section_cap": 800, "curve_power": 0.92, "range_half": 10},
]

SECTION_CONFIG = {
    "english": {"m1_total": 27, "m2_total": 27, "bands": DEFAULT_BANDS},
    "math":    {"m1_total": 22, "m2_total": 22, "bands": DEFAULT_BANDS},
}
```

```python
# apps/sat/libs/calculator.py:67-95 (core formula)
def _calculate_section_score(m1_correct: int, m2_correct: int, *, section_key: str) -> dict:
    config = SECTION_CONFIG[section_key]
    m1_ratio = _clamp(m1_correct / config["m1_total"], 0.0, 1.0)
    m2_ratio = _clamp(m2_correct / config["m2_total"], 0.0, 1.0)

    band = _get_band(m1_ratio, config["bands"])
    adjusted_m2_ratio = _clamp(m2_ratio * band["m2_multiplier"], 0.0, 1.0)

    m2_weight = band["m2_weight"]
    m1_weight = 1.0 - m2_weight
    combined_ratio = _clamp((m1_weight * m1_ratio) + (m2_weight * adjusted_m2_ratio), 0.0, 1.0)

    raw_score = 200 + ((combined_ratio ** band["curve_power"]) * (band["section_cap"] - 200))
    score = int(_clamp(_round_to_ten(raw_score), 200, band["section_cap"]))
    ...
```

In plain terms: a student's Module‑1 accuracy selects a "band" (low/mid/high), which determines (a) how heavily Module 2 counts (36–48%), (b) a multiplier applied to Module 2's ratio (0.92–1.05×), and (c) a **hard cap on the section score** (650/730/800) — a student who does poorly on Module 1 cannot reach 800 regardless of Module 2 performance, approximating real adaptive-SAT score compression without actually branching question content. The weighted ratio is then raised to a `curve_power` exponent and mapped linearly into `[200, cap]`, rounded to the nearest 10.

Total score is a **plain sum**: `total = english_section_score + math_section_score` (`calculator.py:107`), giving 400–1600. **No documented derivation exists for the specific constants** (27/22 question counts, 0.45/0.75 band cutoffs, 650/730/800 caps, 0.92–1.02 curve powers) — treat them as product-tuned heuristics, not verified psychometric equating, when deciding whether to port them as-is.

A **second scoring path** exists for Guest Mode / global events (`apps/sat/guest_views.py`) — it reuses the same `calculator.py` for complete two-module attempts, with a distinct 200–600 "Level Check" fallback table (`RAW_TO_EQUIV`, `guest_views.py:566-592`) for single-module/short guest tests. A **third, orphaned scoring module** (`apps/sat/guest_services.py`) computes an unscaled raw count against a `choices`/`is_correct` schema that doesn't match the actual question models and is **imported nowhere else in the codebase** — confirmed dead code, do not port.

#### Question types & grading

| Type | Field | Grading logic |
|---|---|---|
| English multiple-choice | `English_Question.response_type = "multiple_choice"` (default) | Case-insensitive normalized string equality vs. `answer` |
| English open-text ("student-produced response") | `response_type = "open_text"` | Checked against `accepted_answers` (literal list) then `answer_patterns` (regex list), both Unicode-normalized; 15 hardcoded "Placement Test Offline" questions get a bespoke deterministic paraphrase/grammar matcher (`apps/sat/placement_offline_grading.py`) — **explicitly never calls an external/AI service** for grading |
| Math multiple-choice | `Math_Question.written = False` | Same normalized comparison |
| Math grid-in (written) | `Math_Question.written = True` | `check_written()` (`apps/sat/views.py:212`) — supports comma-separated multiple accepted values, decimal-comma→point conversion, and fraction parsing, so `"1/2"`, `"0.5"`, and `".5"` are all correctly treated as equal via `Decimal` arithmetic |
| Vocabulary quiz | separate feature | Plain unnormalized string equality; **does not feed into the 400–1600 SAT score** |
| Essay | — | **Does not exist as a question type anywhere in the codebase** (consistent with the modern digital SAT) |

**No adaptive question-routing exists** — confirmed by grep: `module` choices are only ever `module_1`/`module_2`, with no "easy/hard Module 2" variants anywhere in the schema. Every student taking a given `Test` sees identical Module 2 content regardless of Module 1 performance; only the *scoring formula* (above) simulates adaptive-style compression after the fact.

**Correctness is recomputed live at review/results time**, not stored at submission (`check_english_answer`/`check_written` are re-run against the *current* question record every time results/review are viewed) — so editing a question's answer key after students have taken it will silently change historical results. Flag this as a decision point for the new backend (snapshot-at-submission vs. recompute-on-read).

#### Review/explanation feature

Post-test, `question(request, key, section, module, id)` (`apps/sat/views.py:2675`) serves a per-question review with the stored `explained`/`img_explain` text/image, prev/next navigation ordered by actual question number, and reference-answer resolution for open-text questions. Access is time-boxed per `docs/review_time_policy.md`: **24h / 2 retakes** for regular students, **3 days / 4 retakes** for `OFFLINE`, unlimited for `Admin` — though `get_max_retakes()` currently always returns `None` (unlimited for everyone), meaning the retake-limit UI path is presently unreachable dead code.

#### Progress tracking, mistake tracking, leaderboards

- **Domain-wise breakdown** (8 fixed domain names, e.g. "Algebra", "Craft and Structure") is computed **only** inside certificate generation (`_generate_certificate_response`, `apps/sat/views.py:3229`) — there is no separate always-available student-facing domain-analytics dashboard.
- **Vocabulary mastery**: a simple 3-state classifier (`new`/`learning`/`mastered`), not true spaced repetition — `mastered` when `consecutive_correct >= 2` **or** (`attempts >= 4 and accuracy >= 0.8`); a miss after mastery demotes the word back to `learning` (`apps/sat/vocabulary_progress.py:30-38`).
- **`rankings`** (`/sat/rankings/<pk>`) — top-50 by score, **globally across all classrooms, with no authentication check at all** (flag — likely needs scoping/auth before any mobile equivalent ships).
- **Guest leaderboard** — top-100, names masked (first name + last-initial, or partially redacted single names).
- **`Punishment` model + `/sat/punishment/<pk>` view exist but are dead code** — the view just logs a row and returns a static "Admins will be notified" string; no notification logic exists, and **no client-side code anywhere calls this endpoint or detects any cheating signal** (no tab-switch penalty, no fullscreen enforcement, no copy/paste blocking, no devtools detection). The only client-side "integrity" mechanisms found are a multi-tab lease (prevents two open tabs from racing autosaves) and `visibilitychange`-triggered autosave flushing — neither reports anything to the server as a violation. **There is currently no working anti-cheat/proctoring system to port; if the mobile app needs one, it must be designed new.**

### 4.6 Third-Party Integrations

| Integration | Where | Purpose | Notes |
|---|---|---|---|
| **Cloudflare R2** (S3-compatible) | `apps/sat/storages.py` (`PublicStorage`, `PrivateStorage`) via `django-storages`/`boto3` | Question/choice/explanation images, certificates, raw video uploads | Public bucket unsigned; private bucket signed URLs. Static assets are **not** on R2 (WhiteNoise/local instead) |
| **PyMuPDF (`fitz`)** | `apps/sat/libs/certificate/certificate.py`; `apps/sat/question_audit.py` | Certificate PDF generation (opens a template, overlays score text + a domain-proficiency box grid); internal AI-audit PDF report | Not a network service — local PDF library |
| **SMTP email** | `django.core.mail`, configurable host (default `smtp.gmail.com`) | Password-reset codes only | Registration verification email is currently not sent (see 4.3) |
| **Google OAuth** | `django-allauth` | Social login | No custom adapter found |
| **OpenAI API** | `apps/sat/question_audit.py`, raw `urllib` calls to `/v1/responses` | Admin-only, CLI-triggered question-bank quality audit | Confirmed **student data is never sent** — payload is built strictly from question-bank fields, never from attempt/score tables. Not reachable from any web view |
| **Telegram (aiogram)** | `apps/telegram_bot/` | Internal admin tool: bulk-create student accounts via a Telegram chat bot | Not student-facing, not a notification channel, runs as its own Docker service |
| **Payment/subscription providers** | — | **None found anywhere** — a repo-wide grep for payment/stripe/payme/click.uz/paycom/subscription/premium/price/tariff/billing/invoice/paywall returned zero genuine hits (all hits were false positives: a Bootstrap Icons glyph literally named "stripe", and a CSS comment using "premium" to mean UI polish) | Confirms the audit brief's premise: no payment code exists, dormant or otherwise |

**Broken/vestigial integration to flag**: `apps/sat/tasks.py` imports Celery and defines an HLS video-conversion task that shells out to `ffmpeg` — but Celery isn't installed, there's no broker configured, and the function is never called from anywhere in the codebase. This is dead code from an apparently-abandoned video-streaming feature; do not treat it as a working reference implementation.

### 4.7 Security Measures

- **Rate limiting** exists in a few specific places (all using Django's default in-process cache — see [4.8](#48-caching) for a caveat): classroom join-code submission (5 attempts / 10 min, per IP), guest/global-event access-code entry (10 failures / 15 min, per session), password-reset code attempts (5 tries then invalidated). **Login itself has no rate limiting or lockout** — a gap worth closing for a public-facing mobile API.
- **CSRF**: Django's standard CSRF middleware, custom-named cookie, `SameSite=Lax`. All state-changing AJAX endpoints send `X-CSRFToken`.
- **CORS**: No `django-cors-headers` or equivalent found — the app doesn't need CORS today because there's no cross-origin API consumer. A mobile backend **will** need explicit CORS/API-auth design since it's a new consumer by definition.
- **Input validation**: Django Forms throughout (`apps/base/forms.py`, `apps/sat/forms*.py`) plus hand-written normalization/validation for exam answers (`_normalize_live_test_answer`, answer length caps, allowed-letter checks).
- **Secrets/env vars**: `.env` (git-ignored) loaded via `python-dotenv`; `SECRET_KEY` falls back to a `config.ini` file if the env var is absent. R2 credentials, email credentials, `OPENAI_API_KEY`, Google OAuth client secret all sourced from environment variables — no secrets hardcoded in source that this audit found (values were not inspected/exfiltrated, only key names).
- **Known concerns to flag explicitly**:
  - `admin_mock_download` streams **plaintext** bulk-generated student passwords as a downloadable `.txt` file, re-downloadable indefinitely (`Mock.credentials` TextField stores them in the clear).
  - `telegram_bot.GeneratedUser.password` field is documented as storing a raw/unhashed temporary password (though in the current code path it's actually created blank — inconsistent handling worth resolving).
  - `rankings` view has zero authentication or classroom scoping — leaks usernames + scores across classroom boundaries to any visitor.
  - `@allowed_users(...)` decorator doesn't verify `is_authenticated` before touching `request.user.groups`, and two Admin-only views (`results_by_user`, `certificate_by_user`) rely on it **without** also stacking `@login_required` — behavior for anonymous requests wasn't verified at runtime by this audit.
  - `ClientSoftwareMiddleware`'s "official desktop client" gate is a plain User-Agent string match (`MakonBookClient/1.0`) — trivially spoofable, not a real security boundary.

### 4.8 Caching

**No `CACHES` setting is configured** in `satmakon/settings.py` — Django falls back to its default `LocMemCache` (per-process, in-memory, **not shared** across gunicorn's multiple worker processes). The Django cache framework is used in exactly one place: the rate-limiting counters described above (`django.core.cache.cache`, `apps/sat/views.py`). **Because this cache is per-process, a client can get up to `workers × limit` attempts before being throttled** — a real correctness gap if this rate-limiting approach is ported as-is; the new backend should use a shared cache (Redis) for any rate-limiting/counter logic. No page/fragment caching, no `@cache_page`, exists anywhere.

---

## 5. Frontend Deep-Dive

**Architecture confirmed: no separate frontend framework.** No `package.json`, no `node_modules`, no React/Vue/Angular anywhere in the repo. This is 100% server-rendered Django templates styled with **two coexisting Bootstrap versions** (4.3.1 for the main app, 5.3.3 vendored with a separate landing-page theme — a real consistency debt) plus hand-written vanilla JS/jQuery loaded per-page via `<script>` tags. `staticfiles/` is confirmed pure `collectstatic` output, not source.

### Template inventory (grouped by area)

- **Landing/marketing**: `landing/home.html`, `base/home.html`, `base/team.html`, `software.html`
- **Auth/account**: `base/login.html`, `register.html`, `verify.html`, `forgot_password.html`, `password_reset_confirm.html`, `edit_profile.html`, `profile_name_prompt.html`
- **Student exam-taking**: `test/dashboard.html`, `test/test_eng.html`/`test_math.html`, `test/test_modules.html`, `test/makeup_*`, `test/results.html`, `test/shared/attempt_eng.html`/`attempt_math.html` (the actual reusable exam UI, also reused by classroom/makeup/guest flows), `test/review/*`, `test/features/rankings.html`, `sat/enter_code.html`, `sat/practice_tests.html`
- **Guest/global-events**: `sat/guest/entry.html`, `attempt*.html`, `result.html`, `review.html`, `event_list.html`, `leaderboard.html`
- **Vocabulary**: `sat/vocabulary*.html`, `sat/vocabulary_flashcards.html`, `practice_quiz*.html` (+ teacher content-management templates)
- **Admissions**: `sat/admissions.html`, `admissions_section.html`
- **Classroom**: `sat/classroom_join.html`, `student_classroom_home.html`, `classroom_chat.html`, `classroom_progress_dashboard.html`, plus teacher-side management templates
- **Support-teacher**: `sat/support_teacher_list.html`, `support_teacher_detail.html`, `my_support_lessons.html`, `support_teacher_planner.html`
- **Student goals**: `sat/student_goal_settings.html`, `_student_goal_modal.html`
- **Ratings**: `ratings/student_dashboard.html`, `public_board.html`, `parent_lookup.html`
- **AP Classes**: `apclasses/student/exam_list.html`, `exam_detail.html`, `exam_part.html`, `exam_frq.html`
- **Internal admin panel** (custom, distinct from Django's `/admin/`): `sat/admin/*` (dashboard, tests, mocks, groups, users, support-teachers)
- **Emails**: `emails/password_reset_code.{html,txt}`
- Stray finding: `templates/test/temp` is a leftover Python management script accidentally committed inside the templates folder — cleanup debt, not a template.

### State management approach

None needed/used in the SPA sense — pages are server-rendered. In-page interactivity uses vanilla JS module state plus deliberate use of `localStorage` as a durability layer for exam answers (mirrored alongside every server autosave, merged by timestamp on reload) and for a couple of small UI preferences (theme, review-answer-visibility toggle).

### Key student flows

**Registration/login**: standard HTML forms, full-page POST, Django messages framework for errors; Google OAuth via allauth's own redirect flow.

**Dashboard (`classroom_entry` / `/sat/`)**: routes by role, then renders either a classroom-status screen or the global practice-tests dashboard with per-test progress badges.

**Taking an exam** — the most heavily engineered flow, driven by `static/assets/js/sat-test-core-v13.js` (~1046 lines, shared engine) + `test-eng.js`/`test-math.js` (section-specific renderers) + `sat-math-tools-v13.js` (Desmos calculator + reference sheet popup):
- **Timer**: countdown rendered from a server-provided absolute `deadlineAt` epoch vs. `Date.now()`, re-synced on every autosave response — not a naive client-decremented counter (matches the server-authoritative design in 4.5).
- **Navigation**: all questions for the current module are serialized into the page on load; `next()`/`previous()`/`goTo()` just repaint via `innerHTML` — **no network round-trip per question**.
- **Autosave**: debounced on every answer/eliminate/mark-for-review change (900ms) and on navigation (1300ms), plus a 20s background flush, `visibilitychange`-triggered flush, and a `beforeunload` local-storage save + native "leave site?" prompt. A `localStorage`-based multi-tab lease prevents two open tabs from racing autosaves against each other.
- **Submission**: a confirm modal → POST with a client-generated idempotency id → for guest attempts, a status-polling fallback if the initial POST times out.
- **Math tools**: Desmos calculator (script loaded at runtime) + a static reference-sheet overlay; math rendering uses **KaTeX 0.15.3 loaded from a public CDN** — a hard external/online dependency with no offline fallback today, relevant for mobile offline-mode planning.
- **Anti-cheat**: confirmed **none** exists client-side (no fullscreen lock, no copy/paste blocking, no devtools detection, no tab-switch penalty) — see 4.5.

**Results/certificate**: `test/results.html` shows per-module breakdown; certificate is generated server-side as a PDF (no template render) and served via a signed R2 URL.

**Review/explanations**: `test/review/test_eng.html`/`test_math.html`, prev/next navigation, explanation text/image inline.

**Profile/settings**: `edit_profile.html` (offline-group users can set custom section time limits), `profile_name_prompt.html` (name-completion prompt).

### UI component library / design system

- **Bootstrap 4.3.1** (main app) and **Bootstrap 5.3.3** (vendored landing-page theme, "Impact" BootstrapMade template) coexist with no shared token layer — a real consistency debt.
- **Two icon libraries**: Font Awesome 4.7.0 (app-wide, including the exam window) and Bootstrap Icons (landing page only) — not unified.
- No formal design-system documentation, no Storybook, no design tokens file. The clearest paper trail of "design decisions" is actually a large set of sequentially-numbered/hotfix-suffixed CSS files (see below) — read those as reactive patches, not an intentional spec.

### Form handling & validation

Django Forms server-side (`apps/base/forms.py`, `apps/sat/forms*.py`, `apps/sat/student_goal_forms.py`, `apps/sat/support_forms.py`) with matching but independent client-side JS validation on a few forms (e.g. profile-name gate accepts Uzbek/Russian characters, hyphens, apostrophes). No shared client/server validation-schema layer (no JSON Schema, no shared Zod-equivalent) — validation rules are duplicated by hand where both layers exist.

### Localization / i18n

**Correction to the audit brief's premise: there is no site-wide i18n framework.** `USE_I18N=True` is set but there's no `LANGUAGES` setting, no `locale/` directory, no `LocaleMiddleware`, and no real usage of `{% trans %}`/`{% blocktrans %}` anywhere. The **only** actual translation mechanism in the entire codebase is a hand-rolled, single-page dictionary in `apps/ratings/views.py` (`PARENT_TRANSLATIONS`, English/Russian/Uzbek), used exclusively by the parent-facing rating-lookup page, with language chosen via `?lang=`, then session, then `Accept-Language` header. **Uzbek/Russian/English are indeed the three target languages**, but full UI translation coverage does not exist today anywhere else (exam-taking, dashboards, classroom, vocabulary — all English-only). A mobile app needing multi-language support will need this built essentially from scratch, informed only by this one page's pattern.

### Real-time / polling features

No WebSockets/SSE anywhere. Two independent polling mechanisms, both plain `setInterval` + `fetch`/reload:
1. **Classroom chat** — adaptive interval, 3s while the tab is visible / 15s while hidden, cursor-based (`?last_id=`) incremental fetch.
2. **Classroom join-status** — cruder: polls every ≥3–5s and does a **full page reload** rather than a fetch, when visible and the user isn't actively typing a code.

---

## 6. Data Models Reference

This section is the authoritative field-level schema reference for designing the new mobile backend's data model. Grouped by app; only models relevant to students/exam content are detailed in full (teacher/admin-only management scaffolding is named but not exhaustively field-listed).

### `apps.base`

| Model | Key fields | Relationships |
|---|---|---|
| `EmailVerification` | `token` (UUID, unique), `is_verified`, `expires_at` (default now+24h) | FK → `User` |
| `PasswordResetCode` | `code_hash`, `expires_at` (now+10min), `attempts`, `is_used` | FK → `User` |
| `UserProfile` | `english_time_minutes` (default 32), `math_time_minutes` (default 35) | 1:1 → `User` |
| `GeneralIssueReport` | `category`, `message`, `page_url`, `context_data` (JSON), `status` | FK → `User` (nullable) |

### `apps.sat` — question bank & test structure

| Model | Key fields | Relationships |
|---|---|---|
| `QuestionDomain` | `name` | — |
| `QuestionType` | `name` | FK → `QuestionDomain` |
| `Test` | **`name` (PK, string)**, `groups` (M2M), `icon` | M2M → `Group` |
| `English_Question` | `module` (`module_1`/`module_2`), `number`, `passage`, `question`, `a/b/c/d`, `response_type` (`multiple_choice`/`open_text`), `answer`, `accepted_answers`, `answer_patterns`, `explained`, `image`, `graph` | FK → `Test`, `QuestionDomain`, `QuestionType` |
| `Math_Question` | Same core fields + `written` (bool, grid-in flag), `image_a..d`, `choice_graph`, `img_explain` | FK → `Test`, `QuestionDomain`, `QuestionType` |
| `MakeupTest` | `name`, `description`, `groups` (M2M) | M2M → `English_Question`/`Math_Question` (through ordered tables) |
| `SecretCode` | `code` (6-digit, unique) | FK → `Group`, `MakeupTest` (nullable), `Test` (nullable) |
| `Mock` | `mode` (`secret_code`/`direct`), `user_count`, `credentials` (plaintext — flagged) | FK → `Test`, `Group`, `SecretCode`, `User` (created_by) |

### `apps.sat` — attempt & scoring engine

| Model | Key fields | Relationships |
|---|---|---|
| `TestModule` | `section`, `module` (`m1`/`m2`), `answers` (JSON text), `attempt_id` (UUID), `test_type` (`regular`/`makeup`) | FK → `Test`/`MakeupTest`, `User`, `Classroom` (nullable) |
| `TestModuleDraft` | `answers`/`time_spent`/`eliminated_choices`/`marked_for_review` (JSON lists), `current_question_index`, `deadline_at` | FK → `Test`, `User`, `Classroom` (nullable) — unique per (user,test,attempt_id,section,module) |
| `MakeupTestModuleDraft` | Same shape as above | FK → `MakeupTest`, `User` |
| `TestReview` | `key` (unique share key), `attempt_id`, `score` (int, nullable), `certificate` (path), `domains` (bool flag), `duration` (vestigial — `is_active()` always True) | FK → `Test`/`MakeupTest`, `User`, `Classroom` |
| `TestStage` | `stage` (int, current position), `attempt_id`, `retake_count`, `again` | FK → `Test`/`MakeupTest`, `User`, `Classroom` |
| `Punishment` | `name` (text) | FK → `User` — **dead/unused feature** |

### `apps.sat` — classroom system

| Model | Key fields | Relationships |
|---|---|---|
| `Classroom` | `classroom_type` (`sat`/`ap`), `is_active` | FK → `User` (teacher, single owner) |
| `ClassroomJoinCode` | `code` (6-digit), `expires_at` (default +12h) | 1:1 → `Classroom` |
| `ClassroomMembership` | `role` (`teacher`/`student`), `status` (`pending`/`approved`/`rejected`/`left`/`removed`) | FK → `Classroom`, `User` — unique per (classroom,user) |
| `StudentSectionAccess` | `section` (`practice_tests`/`vocabulary`/`admissions`), `has_access` | FK → `ClassroomMembership` |
| `ClassroomSectionAccessPolicy` | Same 3 sections, classroom-wide default | FK → `Classroom` |
| `ClassroomPracticeTestAccessPolicy` | `access_mode` (`all`/`selected`) | 1:1 → `Classroom`; M2M → `Test` |
| `StudentPracticeTestAccess` | `has_access` | FK → `ClassroomMembership`, `Test` |
| `StudentProgress` | `completion_percent`, `completed_items`/`total_items`, `activity_count` | FK → `Classroom`, `User`, per `section` |
| `ChatMessage` | `message`, `file`, `is_deleted` (soft-delete flag, but the delete view actually hard-deletes — inconsistency flagged) | FK → `Classroom`, `User` (sender) |

### `apps.sat` — guest / no-login exam engine

| Model | Key fields | Relationships |
|---|---|---|
| `GlobalEvent` | `slug`, `access_code`, `start_at`/`end_at`, `always_live`, `status`, `show_score_immediately`, `show_leaderboard`, `allow_resume` | FK → `Test` |
| `GuestParticipant` | `guest_id` (UUID), `full_name`, `display_name`, `session_key` — **no password field** | — |
| `GlobalEventAttempt` | `guest_token` (UUID), `expires_at`, `status`, `score`, `completed_modules` (JSON) | FK → `GlobalEvent`, `GuestParticipant` — unique per (event,guest) |
| `GlobalEventModuleDraft` | Same autosave shape as `TestModuleDraft` | FK → `GlobalEventAttempt` |
| `GlobalEventAnswer` | `question_id` (**raw int, no FK — flag**), `selected_answer`, `is_correct`, `time_spent` | FK → `GlobalEventAttempt` |

### `apps.sat` — vocabulary, goals, support-teacher booking

| Model | Key fields | Relationships |
|---|---|---|
| `VocabularyUnit` / `VocabularyWord` / `VocabularyQuestion` | `title`/`word`/`meaning`/`example`, `order`, `is_active` | Unit 1:N Word/Question |
| `VocabularyWordProgress` | `status` (`new`/`learning`/`mastered`), `times_seen`, `correct_count`/`incorrect_count`, `consecutive_correct`, `mastered_at` | FK → `User`, `Classroom` (nullable = global scope), `VocabularyWord` — unique per (user,classroom,word) |
| `VocabularyQuizAttempt` / `VocabularyQuizAnswer` | `mode`, `selected_units` (JSON), `score`/`total_questions`, `percentage` | FK → `User`, `Classroom` (nullable) |
| `DreamUniversity` | `name`, `country`, `average_sat_score`, `qs_rank` | Admin-curated catalog |
| `StudentGoalProfile` | `target_sat_score` (default 1400), `exam_date` (must match a hardcoded official-SAT-dates list through mid-2027), `daily_study_minutes_goal`, `weekly_study_days_goal` | 1:1 → `User`; FK → `DreamUniversity` (nullable, or custom fields) |
| `SupportTeacherProfile` | `subjects`, `bio`, `sat_total_score`/`sat_math_score`/`sat_reading_writing_score`, `min_booking_notice_hours`, `cancellation_notice_hours` | 1:1 → `User` |
| `SupportTeacherAvailability` | `day_of_week`, `start_time`/`end_time`, `slot_duration_minutes`, `buffer_minutes` | FK → `SupportTeacherProfile` |
| `SupportLessonTitle`/`SupportLessonTopic` | Category taxonomy for bookable topics | Title 1:N Topic |
| `SupportLessonSession` | `start_at`/`end_at`, `status`, `max_students`, `is_open_for_requests` | FK → `SupportTeacherProfile`, `SupportLessonTopic` |
| `SupportLessonBooking` | `status` (`requested`/`scheduled`/`completed`/`cancelled`/`no_show`), `start_at`/`end_at` (null while requested), `cancellation_reason` | FK → `SupportTeacherProfile`, `User` (student), `SupportLessonSession` (nullable) |
| `SupportTeacherReview` | `rating` (1-5), `feedback` (**private, never public**) | 1:1 → `SupportLessonBooking` |

### `apps.apclasses` (AP exam feature)

| Model | Key fields | Relationships |
|---|---|---|
| `APClass` | `name`, `code`, `groups` (M2M) | — |
| `APMockExam` | `part_a_duration_minutes` (default 60, no calc), `part_b_duration_minutes` (default 45, Desmos allowed), `frq_duration_minutes` (default 30) | FK → `APClass` |
| `APMultipleChoiceQuestion` | `part` (`part_a`/`part_b`), `a/b/c/d/e` (**5 choices**), `correct_answer`, `calculator_allowed`/`desmos_allowed` (auto-derived from `part`, not user-settable) | FK → `APMockExam` |
| `APFRQPage` | `page_number`, `instructions`, `image`/`file` | FK → `APMockExam` |
| `APExamEvent` | `is_global`, `classrooms` (M2M → `sat.Classroom`, no DB FK constraint), `max_attempts`, `allow_guest_attempts` | FK → `APMockExam` |
| `APExamAttempt` | `student` (nullable FK) **or** `guest_session_key` — one table for both logged-in and guest attempts | FK → `APExamEvent`, `User` (nullable) |
| `APExamAnswer` | `selected_answer`, `is_correct` (auto-computed on save) | FK → `APExamAttempt`, `APMultipleChoiceQuestion` (proper FK) |
| `APFRQSubmission` | `image`/`file` (uploaded photo of handwritten answer), `score`/`teacher_comment` (human-graded) | FK → `APExamAttempt` |

### `apps.ratings`

| Model | Key fields | Relationships |
|---|---|---|
| `RatingConfig` | Singleton; `alpha` (EWMA weight), `min_assessments_per_classroom`, `top_n` | — |
| `RatingProfile` | `public_visible`, `parent_access_code` (auto-generated) | 1:1 → `User` |
| `RatingAssessment` | 5 sub-scores (`homework`/`progress`/`activity`/`attendance`/`behavior`, 0-10), `comment` | FK → `sat.Classroom`, `User` (student), `User` (teacher) |

### `apps.telegram_bot` (not student-relevant, listed for completeness)

`TelegramAdmin`, `BulkUserRequest`, `GeneratedUser` — internal-only, bulk account provisioning.

### Entity relationship summary (text form)

```
User ─1:1─ UserProfile, RatingProfile, SupportTeacherProfile(opt), StudentGoalProfile
User ─N:N(via ClassroomMembership)─ Classroom ─1:N─ owned by one teacher User
Classroom ─1:N─ StudentSectionAccess/StudentPracticeTestAccess/StudentProgress/ChatMessage (per member)
Test(pk=name) ─1:N─ English_Question/Math_Question(module_1|module_2) ─N:N(via TestModule)─ User attempts
User+Test+attempt_id ─→ TestStage(current position) ─→ TestModuleDraft(autosave) ─→ TestModule(submitted) ─→ TestReview(scored)
GlobalEvent ─1:N─ GlobalEventAttempt ─FK─ GuestParticipant(no account) ─1:N─ GlobalEventModuleDraft/GlobalEventAnswer
APMockExam ─1:N─ APExamEvent ─1:N─ APExamAttempt(User OR guest) ─1:N─ APExamAnswer/APFRQSubmission
```

---

## 7. User Roles & Permissions

### Student — full breakdown (mobile app's only role)

**Can:**
- Register/log in (username+password or Google), reset password, edit profile.
- Optionally join a classroom via a teacher's 6-digit code (subject to teacher approval).
- See and start any `Test` they're entitled to (via Django-group membership if unaffiliated, or via classroom-scoped policy if in a classroom).
- Take a test module-by-module under a server-authoritative timer, with autosave and full resume-from-anywhere.
- Retake a full test or a single section **unlimited times** (the retake-limit mechanism exists in code but is currently disabled/unreachable).
- View scaled results (400–1600), a PDF certificate, and per-question review/explanations (time-boxed per group: 24h/2 retakes standard, 3 days/4 retakes for `OFFLINE` accommodation, unlimited for `Admin`).
- Study vocabulary (flashcards + quizzes, per-word mastery tracking), set a score/university goal, browse static admissions content.
- Book a support-teacher lesson (request a topic; may be auto-grouped into an already-scheduled session or wait for the teacher to schedule one), cancel (subject to notice window), leave private feedback.
- If in a classroom: chat with classmates/teacher (poll-based), see classroom-scoped versions of the above.
- Take AP practice exams (if entitled via classroom/group), including uploading photographed FRQ answers.
- As a **guest** (no account): take public "global event" mock SAT or AP exams anonymously, see a masked leaderboard — but **cannot** later claim/merge that attempt into a real account.

**Cannot:**
- Create/edit questions, tests, or vocabulary content (view-only for all exam/vocabulary content).
- See other students' private support-teacher feedback.
- Approve their own classroom join request, or see other classrooms' rankings/chat.
- Access any Django-admin, custom admin-panel, teacher, or manager route (all separately group/ownership-gated).

### Other roles (brief — web-only, out of mobile scope)

| Role | Mechanism | Summary |
|---|---|---|
| **Teacher** | `is_teacher()` = has `teacher` group **or** owns an active `Classroom` | Owns classrooms, approves/rejects join requests, sets section/test access policy, manages vocabulary content, gives student ratings, chats, views progress dashboards |
| **Support Teacher** | Has a `SupportTeacherProfile` row | Public bookable tutor profile; manages availability, session scheduling, sees (but doesn't publicly show) student feedback |
| **Manager** | `Manager` group | Operational dashboard over teachers/classrooms, no content-editing |
| **Admin / Tester** | `Admin`/`Tester` groups, or `is_staff`/`is_superuser` | Full content management (via Django `/admin/` + a custom `/sat/admin-panel/`), user/group administration, bulk "Mock" session provisioning, unlimited review access |
| **Dev** | `dev` group | Internal QA/debug tooling under `/sat/dev/` |
| **Telegram-bot admin** | Separate `TelegramAdmin` identity, not a Django `User` | Bulk-creates student accounts via a Telegram chat bot — purely an internal ops tool |

---

## 8. Non-Functional Notes

### Testing coverage

17 versioned `test_*.py` files (named after the build/incident they were written for, e.g. `test_guest_scoring_v335.py`, `test_classroom_access_policy_v33_3.py`) plus a larger core suite (`apps/sat/tests.py`, ~47 test methods covering answer matching, classroom approval, vocabulary progress, the full test-flow including timers/autosave/idempotent submission, and guest-mode flow). These are real Django `TestCase`/`SimpleTestCase` suites with proper fixtures, not ad-hoc scripts — but the pattern is clearly **incident-driven regression testing** (each file pins down a specific bug fix or feature at ship time) rather than systematic coverage. Notably dense coverage exists around the exam-taking draft/timer/idempotent-submission logic, implying that area broke in production before and is now heavily guarded. **Large areas have no visible test coverage**: `views_admin.py`, `guest_views.py` beyond scoring math, the Telegram bot, the AI question-audit tool, storage backends, and video/HLS code.

### Performance-relevant details

- `practice_tests` dashboard batches its per-test progress queries (`_split_tests_by_user_progress`) rather than N+1-querying per test card — a positive sign, though the full query surface wasn't exhaustively profiled by this audit.
- `Lesson.get_random_questions()` uses in-memory `random.sample()` over a queryset rather than DB-level random sampling — a possible scale concern if the (currently mostly-unused) Lessons feature is ever revived.
- No explicit pagination was confirmed on the `fetch_classroom_messages` chat-polling endpoint (`?last_id=` cursor exists, but no `LIMIT`) — bounded in practice by polling frequency, but worth adding an explicit cap for a mobile API.
- No caching layer exists beyond Django's default per-process `LocMemCache` (see 4.8) — any high-traffic mobile endpoint (e.g. rankings, question banks) would need real caching designed in.

### Offline handling

**No true offline support exists today.** The exam-taking flow's `localStorage` mirroring is a *resilience* measure for a flaky-but-eventually-connected browser tab, not an offline-first design — every meaningful state transition (autosave, submit) requires a live round trip to the server, and the timer deadline is enforced server-side with no "pause while offline" concept. A mobile app, which will face far more backgrounding/connectivity loss than a desktop browser tab, needs a deliberately new offline strategy (see [9](#9-recommendations-for-the-mobile-app)).

### Technical debt / legacy patterns / code smells worth knowing before rebuilding

- **CSS/JS hotfix-on-hotfix pattern**: e.g. 10 separate stylesheets for the login/register pages alone (`makon-auth.css`, `makon-auth-final-fix.css`, `makon-auth-header-hotfix.css`, `-show-balance-fix`, `-show-clean-fix`, `-show-desktop-fix`, `-show-hard-fix`, `-show-light-fix`, `-show-raise-fix`...), and versioned-but-coexisting duplicates elsewhere (`support-booking-v29.js`/`.css` vs. `v33`, `sat-test-flow-v13` → `sat-test-interactions-v21` → `sat-test-classic-v16`). This indicates iterative patching without consolidation — **treat these files as a signal to re-derive the intended final UI from a live rendered page, not as clean source to port.**
- **Two Bootstrap versions** (4.3.1 app-wide, 5.3.3 vendored for the landing page) and **two icon libraries** (Font Awesome 4.7, Bootstrap Icons) coexist with no shared design tokens.
- **Dead/broken code identified**: the `Punishment`/anti-cheat stub (nothing calls it); `apps/sat/guest_services.py` (orphaned, schema-mismatched scoring stub); `apps/sat/tasks.py`'s Celery-based HLS video conversion (Celery not installed, function never called); `BaseVideo`/`Lesson.videos`/`LessonProgress.check_completion()` (references a non-existent relation, would raise `AttributeError` if invoked); a duplicate, unused `normalize_written_value()` alongside the actually-used `_normalize_written_token()`; `templates/test/temp` (a stray Python script, not a template); `get_max_retakes()` always returning `None` (retake-limit UI path unreachable).
- **Naming/consistency issues**: `module_1`/`module_2` (question bank) vs. `m1`/`m2` (attempt tracking) for the same concept; `Test.name` as a string primary key; `GlobalEventAnswer.question_id` as an unconstrained raw integer (contrast with the AP app's proper FK equivalent); `ChatMessage.is_deleted` exists as a soft-delete field but the actual delete view hard-deletes instead.
- **Security-relevant debt**: plaintext bulk-mock-exam credentials stored and re-downloadable (`Mock.credentials`); an unhashed temporary-password field in the Telegram bot's `GeneratedUser` model; the unauthenticated/unscoped `rankings` view; per-process (non-shared) rate-limiting cache that under-throttles at more than one worker.
- **Historical data event**: a documented full data wipe on **2025-07-29** (`docs/system_cleanup_guide.md`) deleted all `TestReview`/`TestModule` rows and all `User` accounts except one admin, going from 3,855 users / 9,318 reviews / 38,541 modules down to 1/0/0 (question bank content was preserved). Any historical-analytics assumptions should account for this discontinuity. The same event included the SQLite→PostgreSQL migration and a 50-migration-file consolidation down to 2 files (docs describing "2 clean migration files" are now stale — the current repo has accumulated 40 and 32 migration files respectively in `base`/`sat` since then, which is normal incremental history, not a regression).
- **Known, documented, recurring content-quality issues** (per `docs/auth_question_integrity_fix.md` and the `audit_data_integrity[_v2].py` management commands): malformed answer-choice text with leftover label prefixes ("A.", "B)"), Cyrillic/Latin single-letter answer confusion (С/В/Д vs C/B/D), duplicate `(test,module,number)` keys, and duplicate/blank answer choices. A new backend's content-import/validation layer should guard against these proactively rather than assume clean source data.

---

## 9. Recommendations for the Mobile App

*(This section is the author's analysis and recommendation, not a fact about the existing system.)*

### Mobile tech stack: **React Native** (recommended), Flutter as a reasonable alternative

- The web team's actual JS is vanilla/jQuery-level, not React/Vue — so "team already knows React" isn't a strong signal either way here. The recommendation instead rests on the app's requirements: a **timer-driven, form-heavy, largely native-feeling exam UI** with moderate custom animation needs (the web app's own JS shows lightweight reveal/entrance animation patterns, nothing GPU-intensive), plus a need for solid **offline-queue and background-timer** support.
- **React Native** gives faster iteration if any web developers cross over to help (JS/TS skill transfer, even from jQuery), a mature ecosystem for offline-first patterns (WatermelonDB, Redux Persist, background task libraries), and first-class Expo tooling for push notifications/background fetch — directly relevant to the "background timers" and "poor-connectivity autosave" requirements below.
- **Flutter** is a legitimate alternative if the team prefers a single, more predictable rendering engine for pixel-perfect timer UI and smoother custom animations (e.g. a from-scratch Desmos-style calculator or drawing/highlighter tool, which the web app currently sources from a CDN — a mobile app cannot rely on that CDN dependency and will need a native/bundled equivalent either way).
- **Not recommended**: fully native (Swift/Kotlin separately) — doubles the build effort for a first version with a single core flow (the exam engine) that must be replicated pixel/behavior-perfectly across platforms; revisit only if the product later needs deep platform-specific capability (e.g. very tight proctoring/camera integration) that a cross-platform framework can't provide well.

### New backend architecture

**Reuse conceptually, rebuild concretely.** The current Django app has *no JSON API* to build on — reuse means porting the **domain logic and data shapes**, not the code:
- **Directly portable business logic**: the server-authoritative timer/deadline model (`deadline_at` + draft/submit state machine) is well-designed and should be replicated close to as-is — it already solves the hard part (timer integrity independent of client trust). The scoring formula (`calculator.py`) should be ported verbatim initially (it's a closed, well-isolated function) while flagging to the product owner that its curve constants are unverified heuristics, not real College Board data — worth validating/recalibrating during the rebuild rather than treating as gospel.
- **Redesign, don't port**: the auth layer (build real token/JWT or session-based mobile auth with rate-limiting from day one — the web app's login has none); the two-parallel-test-access-systems (unify group-based and classroom-based access into one authorization model); the three-times-duplicated draft/autosave schema (unify into one generic table); the `module_1/module_2` vs `m1/m2` inconsistency (pick one enum).
- **New backend framework choice**: given the team already runs Django/Python in production, a **Django REST Framework (or FastAPI) service** sharing Python domain-logic modules (scoring, answer-matching/normalization — these are pure functions with no Django-ORM coupling and can likely be copied close to verbatim) is the path of least friction, letting scoring/grading logic be shared or kept in sync deliberately rather than reimplemented in a second language.

### Content pipeline: how exam content reaches the new mobile backend

Admins will keep creating tests/questions through the existing Django app; the new backend needs that content without becoming the same monolith. Options, with tradeoffs:

| Option | How it works | Pros | Cons |
|---|---|---|---|
| **A. Shared read replica of the content tables** | New backend reads `Test`/`English_Question`/`Math_Question`/`QuestionDomain`/`QuestionType` directly from a read-replica (or the same DB, read-only credentials) of the existing Postgres | Zero content-sync lag, no new pipeline to build, single source of truth | Tightly couples two backends to one schema forever; any web-side schema change (and there's a history of them — see the module-naming inconsistency) breaks mobile; scaling/ops risk shared |
| **B. One-way export/sync job** | A scheduled job (or a "publish" button in the admin) exports new/changed `Test`+question rows to a content-only format (JSON/CSV) the mobile backend ingests into its own tables | Clean separation, mobile backend owns its own schema/versioning, can reshape content on import (fix the module-naming/PK issues while porting) | Requires building the export job (nothing like it exists today — recall there's currently no bulk-export/import tooling at all), and a sync-lag/staleness window to manage |
| **C. Content-only API on the existing backend** | Add a small set of read-only, content-scoped JSON endpoints to the *existing* Django app (e.g. `/api/content/tests/`, `/api/content/questions/`) that the new mobile backend calls to pull content, while auth/progress/scoring stay entirely on the new backend | Existing backend stays the single content authority without exposing its full schema/DB; smaller surface to secure/version than full DB access; admins' existing workflow is untouched | Still a coupling point (an API contract to maintain across two teams/services); need to decide who "owns" content caching/staleness on the mobile side |

**Recommendation: start with Option C (content-only API), with an eye toward Option B once the mobile backend's own schema stabilizes.** Reasoning: Option A is fastest but creates exactly the kind of fragile coupling this audit found evidence of the team already struggling with (the module-naming/PK inconsistencies, the "two parallel access systems" the audit flagged). Option C lets the new backend evolve its own, cleaner content schema immediately (fixing the `Test.name`-as-PK and `module_1/m1` issues on the way in) while still having a single, versionable integration point with the existing admin tooling. If/when content volume or admin workflow friction demands it, that same content-API's response shape can become the schema for a batch export job (Option B) without redesigning the contract.

### Mobile-specific concerns to plan for

- **Offline/poor-connectivity exam-taking**: the current web design assumes frequent server round-trips (20s autosave interval) and has **no grace period** for a device that goes offline for a whole module — it just force-submits from the last server draft when contact resumes. For mobile, this needs deliberate redesign: a local write-ahead queue of every answer change, an explicit "offline, will sync" UI state, and a defined grace/reconciliation window (e.g., pause the deadline clock, or extend it by the detected offline duration, rather than silently truncating a student's answers) — this is a product decision, not just an engineering one.
- **Push notifications**: none exist today anywhere in the stack (no FCM/APNs integration, no notification model). Net-new work — relevant for exam reminders, classroom-approval status, support-lesson confirmations, chat messages (which currently rely on the student having the chat screen open and polling).
- **Background timers**: since the exam timer is already server-authoritative (`deadline_at`), a mobile app's job is simpler than it might seem — it doesn't need to keep an accurate background timer running, just resync `deadline_at` on foreground/reconnect and render locally in between. Still needs a local notification ("5 minutes left") scheduled against that same deadline for when the app is backgrounded.
- **Anti-cheat/proctoring**: currently doesn't exist at all (web or otherwise) — if this matters for a mobile product (arguably more, since a phone is easier to have a second device next to), it needs to be scoped as new work, not "port the existing system."

### Data/account considerations

- **Recommendation: mobile users should be the same identity as web users** (shared `User`/credentials), not a separate account space — students plausibly move between studying on the web (classroom features, teacher interaction) and mobile (practice/vocabulary on the go), and a split identity would fragment progress and require its own painful merge story. This means the new backend's user table needs a way to either (a) directly share the existing `auth_user` table/credentials store, or (b) implement its own auth but keep a stable, shared external identifier (e.g., email) to link accounts and allow a future data-merge/sync between the two backends' progress records.
- **Guest attempts remain a genuine open decision** (see below) — currently guest/anonymous attempts on the web are permanently orphaned from any later real account; decide up front whether the mobile app should support (and design for) "try before you sign up, keep your result."

---

## 10. Open Questions

Consolidated from every research pass, each requiring a decision or clarification before mobile/backend design can proceed with full confidence.

1. **Email verification**: the schema/flow for real email verification still exists (`EmailVerification`, `/activate/<token>/`) but the live registration path auto-activates and never sends the email. Should the mobile signup flow implement real verification, or intentionally match the web app's current soft/no-verification behavior?
2. **`complete_profile_name`**: could not confirm from `apps/base/views.py` alone whether this is a hard onboarding gate (blocks other pages until a name is set) or a soft, dismissible prompt. Needs confirmation (likely lives in template/JS logic) before deciding whether mobile needs an equivalent forced step.
3. **Guest → registered account conversion**: no merge/link path exists anywhere (SAT guest attempts or AP guest attempts) once a guest later registers. Is "try a test, then sign up and keep the score" a desired product capability for mobile? If yes, this is net-new design, not a port.
4. **Login has no rate-limiting**, unlike password-reset and classroom-join-code flows which do. Intentional gap, or should it be closed as part of the redesign (it should be, for any public mobile API)?
5. **Two parallel test-access systems** (global `Test.groups` vs. classroom-scoped `StudentPracticeTestAccess`) — not clearly reconciled in the current code (e.g., `approve_join_request` seeds section access at `False` by default rather than visibly always applying the classroom-wide policy in the same code path). Needs a single, well-specified authorization model for the new backend rather than inheriting the ambiguity.
6. **Retake limits**: `get_max_retakes()` always returns `None` (unlimited) — is unlimited retakes the intended product behavior, or is enforcing a cap on the roadmap? This materially affects both scoring-history UX and backend storage growth.
7. **`Punishment`/anti-cheat**: confirmed dead code with no caller. Was this feature deliberately removed, or is it an unfinished stub the team intends to complete? Relevant before assuming "there's no anti-cheat need" is itself a settled product decision rather than an accident.
8. **Rankings/leaderboard scope**: the existing `rankings` view is fully public/unauthenticated and spans all classrooms for a test. Is that the intended visibility model, or should a mobile equivalent be scoped to the student's own classroom/cohort and require auth?
9. **Adaptive difficulty**: the current platform does not implement real Module-2-difficulty branching (only a scoring-formula approximation of adaptive compression). Is building genuine adaptive routing in scope for the new backend, given this is a defining feature of the real digital SAT?
10. **Scoring curve provenance**: the `calculator.py` band constants (question counts, ratio cutoffs, section caps, curve powers) have no documented derivation anywhere in the codebase or `docs/`. Should these be validated/recalibrated against real College Board concordance data as part of the rebuild, or intentionally kept as-is for continuity with existing certificates/results?
11. **Content pipeline mechanism** (Section 9's Option A/B/C): which approach does the team prefer, and does it change based on expected admin-side content-update frequency (daily edits vs. occasional new test drops)?
12. **Shared vs. separate mobile identity**: confirm the recommendation in Section 9 (shared `User`/credentials) against any constraint this audit couldn't see (e.g., planned separate mobile-only signup flows, data-residency requirements, or a desire to keep mobile fully decoupled from the legacy `auth_user` table for migration-risk reasons).
13. **Payment/monetization roadmap**: confirmed no payment code exists today (not even dormant). Should the new backend's schema anticipate future paid tiers (e.g., reserve fields/tables now) even though it's explicitly out of scope for this phase?
14. **i18n scope**: the audit brief assumed broader existing localization than what's actually implemented (only one page has real EN/RU/UZ support). Does the mobile app need full multi-language UI from day one, and if so, is the `apps/ratings` pattern (per-page dictionaries) an acceptable model to extend, or should a proper i18n framework be introduced for both platforms simultaneously?
15. **Video/HLS feature**: `BaseVideo` and the Celery-based HLS conversion pipeline are both broken/dead code, suggesting an abandoned or paused video-lessons feature. Is video content (lesson videos, explanation videos) in scope for the mobile app's first version, and if so, does it need to be designed fresh (nothing here is reusable as working code, only as a rough shape of intent)?

---

*End of audit. All findings above are traceable to specific files in the repository at the path this audit was run against; line numbers are cited inline where the underlying research reports included them.*
