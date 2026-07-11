from __future__ import annotations

import csv
import json
import re
import uuid
from collections import defaultdict
from pathlib import Path

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import identify_hasher, is_password_usable
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.base.models import UserProfile
from apps.sat.models import English_Question, Math_Question, TestModule, TestReview

LABEL_PREFIX = {
    'A': re.compile(r"^\s*(?:A|А)\s*[\.)\-:]\s+", re.I),
    'B': re.compile(r"^\s*(?:B|В)\s*[\.)\-:]\s+", re.I),
    'C': re.compile(r"^\s*(?:C|С)\s*[\.)\-:]\s+", re.I),
    'D': re.compile(r"^\s*(?:D|Д)\s*[\.)\-:]\s+", re.I),
}
DOUBLE_PREFIX = {
    'A': re.compile(r"^\s*(?:A|А)\s*(?:A|А)\b", re.I),
    'B': re.compile(r"^\s*(?:B|В)\s*(?:B|В)\b", re.I),
    'C': re.compile(r"^\s*(?:C|С)\s*(?:C|С)\b", re.I),
    'D': re.compile(r"^\s*(?:D|Д)\s*(?:D|Д)\b", re.I),
}
CYR_TO_LAT = str.maketrans({'А':'A','а':'A','В':'B','в':'B','С':'C','с':'C','Д':'D','д':'D'})
PLACEHOLDER_RE = re.compile(r"^\s*(passage|question|text|none|null|n/a|-|—)\s*$", re.I)
GENERIC_QUESTION_RE = re.compile(r"^(which choice|the text|based on the text|as used in the text|which quotation|according to the text)", re.I)


def norm_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def short(value, n=180):
    value = norm_text(value)
    return value[:n] + ("…" if len(value) > n else "")


def has_real_image_field(obj, field_name):
    try:
        file_field = getattr(obj, field_name, None)
        return bool(file_field and getattr(file_field, 'name', ''))
    except Exception:
        return False


def has_main_image(obj):
    return has_real_image_field(obj, 'image')


def has_all_choice_images(obj):
    return all(has_real_image_field(obj, f'image_{x}') for x in 'abcd')


def normalized_answer(value):
    return norm_text(value).translate(CYR_TO_LAT).upper()


class Command(BaseCommand):
    help = "Safer audit of MakonBook users and SAT question integrity with fewer false positives."

    def add_arguments(self, parser):
        parser.add_argument('--export-dir', default='data_audit_reports_v2')
        parser.add_argument('--smoke-auth', action='store_true')

    def handle(self, *args, **options):
        export_dir = Path(options['export_dir'])
        export_dir.mkdir(parents=True, exist_ok=True)
        auth_rows = []
        q_rows = []
        summary = []
        self.audit_auth(auth_rows, summary, options['smoke_auth'])
        self.audit_questions(q_rows, summary)
        self.audit_saved_attempts(q_rows, summary)
        self.write_csv(export_dir / 'auth_issues_v2.csv', auth_rows, ['severity','issue','user_id','username','email','details'])
        self.write_csv(export_dir / 'question_issues_v2.csv', q_rows, ['severity','section','issue','test','module','number','question_id','details'])
        (export_dir / 'summary_v2.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f"Auth issues: {len(auth_rows)}"))
        self.stdout.write(self.style.SUCCESS(f"Question issues: {len(q_rows)}"))
        self.stdout.write(self.style.SUCCESS(f"Reports written to {export_dir}"))

    def write_csv(self, path, rows, fields):
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, '') for k in fields})

    def add_auth(self, rows, severity, issue, user=None, details=''):
        rows.append({
            'severity': severity,
            'issue': issue,
            'user_id': getattr(user, 'id', '') if user else '',
            'username': getattr(user, 'username', '') if user else '',
            'email': getattr(user, 'email', '') if user else '',
            'details': details,
        })

    def add_q(self, rows, severity, section, issue, obj=None, details=''):
        rows.append({
            'severity': severity,
            'section': section,
            'issue': issue,
            'test': str(getattr(obj, 'test', '') or '') if obj else '',
            'module': getattr(obj, 'module', '') if obj else '',
            'number': getattr(obj, 'number', '') if obj else '',
            'question_id': getattr(obj, 'id', '') if obj else '',
            'details': details,
        })

    def audit_auth(self, rows, summary, smoke_auth=False):
        User = get_user_model()
        users = list(User.objects.all().order_by('id'))
        summary += [
            '# MakonBook Data Integrity Audit V2',
            f'Generated at: {timezone.now().isoformat()}',
            '',
            '## Auth/User',
            f'Users: {len(users)}',
        ]
        email_groups = defaultdict(list)
        username_groups = defaultdict(list)
        for u in users:
            if not norm_text(u.username):
                self.add_auth(rows, 'ERROR', 'blank_username', u)
            if not norm_text(u.email):
                self.add_auth(rows, 'WARN', 'blank_email', u)
            else:
                email_groups[norm_text(u.email).lower()].append(u)
            if norm_text(u.username):
                username_groups[norm_text(u.username).lower()].append(u)
            if not is_password_usable(u.password):
                self.add_auth(rows, 'INFO', 'unusable_password_google_only_or_no_password', u)
            else:
                try:
                    identify_hasher(u.password)
                except Exception as exc:
                    self.add_auth(rows, 'ERROR', 'invalid_or_plain_password_hash', u, str(exc))
            if not UserProfile.objects.filter(user=u).exists():
                self.add_auth(rows, 'ERROR', 'missing_user_profile', u)
        for email, group in email_groups.items():
            if len(group) > 1:
                self.add_auth(rows, 'ERROR', 'duplicate_email_case_insensitive', None, f"{email}: {[u.id for u in group]}")
        for username, group in username_groups.items():
            if len(group) > 1:
                self.add_auth(rows, 'ERROR', 'duplicate_username_case_insensitive', None, f"{username}: {[u.id for u in group]}")
        if smoke_auth:
            marker = uuid.uuid4().hex[:10]
            username = f'audit_tmp_{marker}'
            email = f'audit_tmp_{marker}@example.com'
            password = f'AuditTmp!{marker}123'
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=username, email=email, password=password, is_active=True)
                    authed = authenticate(username=username, password=password)
                    if not authed or authed.id != user.id:
                        self.add_auth(rows, 'ERROR', 'smoke_auth_failed', user)
                    raise RuntimeError('rollback temporary audit user')
            except RuntimeError as exc:
                if str(exc) != 'rollback temporary audit user':
                    raise

    def audit_questions(self, rows, summary):
        summary += ['', '## SAT Questions']
        for model, section in [(English_Question, 'english'), (Math_Question, 'math')]:
            qs = list(model.objects.select_related('test').all().order_by('test_id','module','number','id'))
            summary.append(f'{section}: {len(qs)} questions')
            dup_keys = defaultdict(list)
            qtext_groups = defaultdict(list)
            passage_groups = defaultdict(list)
            for q in qs:
                test_name = str(q.test or '')
                dup_keys[(q.test_id, q.module, q.number)].append(q)
                qnorm = norm_text(q.question).lower()
                pnorm = norm_text(q.passage).lower()
                if qnorm:
                    qtext_groups[qnorm].append(q)
                if section == 'english' and pnorm:
                    passage_groups[(q.test_id, q.module, pnorm)].append(q)

                if not q.test_id:
                    self.add_q(rows, 'ERROR', section, 'missing_test', q)
                if not q.module:
                    self.add_q(rows, 'ERROR', section, 'missing_module', q)
                if q.number is None:
                    self.add_q(rows, 'ERROR', section, 'missing_number', q)

                question_text = norm_text(q.question)
                if not question_text:
                    if section == 'math' and has_main_image(q):
                        self.add_q(rows, 'INFO', section, 'image_only_question_text_blank', q, 'question text blank but main image exists')
                    else:
                        self.add_q(rows, 'ERROR', section, 'blank_question_no_image', q)
                elif PLACEHOLDER_RE.match(question_text):
                    self.add_q(rows, 'ERROR', section, 'placeholder_question', q, short(q.question))

                if section == 'english':
                    passage = norm_text(q.passage)
                    if not passage:
                        self.add_q(rows, 'WARN', section, 'blank_passage', q)
                    elif PLACEHOLDER_RE.match(passage):
                        self.add_q(rows, 'ERROR', section, 'placeholder_passage', q, short(q.passage))

                ans_raw = norm_text(q.answer)
                ans = normalized_answer(q.answer)
                is_written = bool(getattr(q, 'written', False))
                if not ans_raw:
                    self.add_q(rows, 'ERROR', section, 'blank_answer', q)
                elif section == 'english' or not is_written:
                    if ans in {'A','B','C','D'} and ans_raw.upper() != ans:
                        self.add_q(rows, 'WARN', section, 'cyrillic_or_mixed_choice_answer', q, f"raw={ans_raw!r}; normalized={ans}")
                    elif ans not in {'A','B','C','D'}:
                        if section == 'math' and re.search(r"^-?\d+(?:\.\d+)?(?:/\d+)?$", ans_raw):
                            self.add_q(rows, 'ERROR', section, 'numeric_answer_but_written_flag_false', q, f"answer={ans_raw!r}")
                        else:
                            self.add_q(rows, 'ERROR', section, 'invalid_mcq_answer', q, f"answer={ans_raw!r}")

                need_choices = (section == 'english') or (section == 'math' and not is_written)
                if need_choices:
                    choice_graph = bool(getattr(q, 'choice_graph', False))
                    for letter, field in [('A','a'),('B','b'),('C','c'),('D','d')]:
                        value = norm_text(getattr(q, field, None))
                        img_ok = section == 'math' and choice_graph and has_real_image_field(q, f'image_{field}')
                        if not value and not img_ok:
                            self.add_q(rows, 'ERROR', section, f'blank_choice_{letter}', q)
                        elif value and (LABEL_PREFIX[letter].match(value) or DOUBLE_PREFIX[letter].match(value)):
                            self.add_q(rows, 'WARN', section, f'choice_{letter}_contains_real_label_prefix', q, short(value))
                    choices = []
                    for field in ['a','b','c','d']:
                        value = norm_text(getattr(q, field, '')).lower()
                        if value:
                            choices.append(value)
                    if len(set(choices)) < len(choices):
                        self.add_q(rows, 'WARN', section, 'duplicate_choice_text', q, f'choices={choices}')

            for key, group in dup_keys.items():
                if len(group) > 1:
                    for q in group:
                        self.add_q(rows, 'ERROR', section, 'duplicate_question_number_in_test_module', q, f"ids={[x.id for x in group]}")

            for qnorm, group in qtext_groups.items():
                if len(group) > 1:
                    # Generic SAT prompts repeat constantly; they are not reliable evidence of wrong passage.
                    if len(qnorm) < 55 or GENERIC_QUESTION_RE.match(qnorm):
                        continue
                    passage_set = {norm_text(g.passage).lower() for g in group}
                    test_set = {g.test_id for g in group}
                    if len(passage_set) > 1:
                        for q in group:
                            self.add_q(rows, 'WARN', section, 'same_specific_question_text_different_passage', q, f"other_ids={[g.id for g in group if g.id != q.id]}; question={short(q.question)}")
                    elif len(test_set) > 1:
                        for q in group:
                            self.add_q(rows, 'INFO', section, 'same_specific_question_reused_across_tests', q, f"other_ids={[g.id for g in group if g.id != q.id]}")

            if section == 'english':
                for (_test, _module, _passage), group in passage_groups.items():
                    nums = sorted(g.number for g in group if g.number is not None)
                    if len(nums) >= 2 and nums != list(range(nums[0], nums[-1] + 1)):
                        for q in group:
                            self.add_q(rows, 'WARN', section, 'same_passage_non_contiguous_question_numbers', q, f"numbers={nums}; ids={[g.id for g in group]}")

    def audit_saved_attempts(self, rows, summary):
        summary += ['', '## Attempts/Results', f'TestModule rows: {TestModule.objects.count()}', f'TestReview rows: {TestReview.objects.count()}']
        for m in TestModule.objects.select_related('test','user').all().order_by('-created')[:5000]:
            try:
                payload = json.loads(m.answers or '{}')
            except Exception as exc:
                rows.append({'severity':'ERROR','section':m.section,'issue':'invalid_answers_json','test':str(m.test or ''),'module':m.module,'number':'','question_id':'','details':f'TestModule id={m.id}: {exc}'})
                continue
            answers = payload.get('answers')
            if answers is None:
                rows.append({'severity':'WARN','section':m.section,'issue':'answers_payload_missing_answers_key','test':str(m.test or ''),'module':m.module,'number':'','question_id':'','details':f'TestModule id={m.id}'})
            elif not isinstance(answers, list):
                rows.append({'severity':'ERROR','section':m.section,'issue':'answers_payload_answers_not_list','test':str(m.test or ''),'module':m.module,'number':'','question_id':'','details':f'TestModule id={m.id}'})
