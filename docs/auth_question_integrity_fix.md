# MakonBook Auth + Question Integrity Fix

This build contains code-level fixes and safe database cleanup commands.

## Fixed in code

- Login accepts username **or email**.
- Registration checks username/email case-insensitively.
- Registration validates password using Django password validators.
- Edit profile blocks duplicate emails.
- Registration no longer hashes password twice.
- Login page label now says `Username or email`.

## Safe data cleanup commands

Run dry-run first:

```powershell
python manage.py cleanup_data_integrity --all --export-dir data_cleanup_reports
```

Review:

```text
data_cleanup_reports/auth_cleanup_actions.csv
data_cleanup_reports/question_cleanup_actions.csv
data_cleanup_reports/cleanup_summary.md
```

Apply safe fixes only after reviewing the CSVs:

```powershell
python manage.py cleanup_data_integrity --all --apply --export-dir data_cleanup_reports_apply
```

What it fixes automatically:

- Duplicate emails: keeps the account with most activity and archives duplicate account emails as `archived-user-ID@makonbook.local`.
- Duplicate usernames differing only by case: keeps the account with most activity and renames duplicates as `username_ID`.
- Choice prefixes like `A.`, `B)`, `C -` inside answer options.
- Cyrillic lookalike answers like `С`/`В` to Latin `C`/`B`.
- Numeric math answers with `written=False` become written/grid-in questions.

What it does **not** fix automatically:

- Blank answers.
- Missing tests.
- Duplicate question numbers inside one test/module.
- Passage/question semantic mismatch.
- Blank question text with no image.

Those need manual review:

```powershell
python manage.py export_manual_question_review --export-dir manual_review_reports
```

Then review:

```text
manual_review_reports/manual_question_review.csv
```

## Important

Do not run destructive database changes without a backup:

```powershell
python manage.py dumpdata auth.User sat.TestModule sat.TestReview sat.English_Question sat.Math_Question > before_cleanup_backup.json
```
