from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.sat.models import Classroom, SupportTeacherProfile
from apps.sat.roles import (
    SUPPORT_TEACHER_GROUP,
    TEACHER_GROUP,
    in_group,
    is_support_teacher,
    is_teacher,
)


class Command(BaseCommand):
    help = "Audit group-authoritative Teacher and Support Teacher role integrity."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Audit one username only.")

    def handle(self, *args, **options):
        User = get_user_model()
        username = (options.get("username") or "").strip()
        users = User.objects.all().order_by("username")
        if username:
            users = users.filter(username__iexact=username)

        found = 0
        for user in users:
            owns = list(Classroom.objects.filter(teacher=user).values_list("id", "name"))
            try:
                support_profile = user.support_teacher_profile
            except Exception:
                support_profile = None

            mismatch = bool(
                (owns and not in_group(user, TEACHER_GROUP))
                or (support_profile and not in_group(user, SUPPORT_TEACHER_GROUP))
            )
            if username or mismatch:
                found += 1
                groups = list(user.groups.order_by("name").values_list("name", flat=True))
                self.stdout.write(self.style.WARNING(f"User: {user.username}" if mismatch else f"User: {user.username}"))
                self.stdout.write(f"  Groups: {', '.join(groups) if groups else '(none)'}")
                self.stdout.write(f"  Django flags: is_staff={user.is_staff}, is_superuser={user.is_superuser}, is_active={user.is_active}")
                self.stdout.write(f"  Effective Teacher: {is_teacher(user)}")
                self.stdout.write(f"  Owned classrooms: {len(owns)}")
                for classroom_id, name in owns[:10]:
                    self.stdout.write(f"    - #{classroom_id} {name}")
                self.stdout.write(f"  Support profile: {'yes' if support_profile else 'no'}")
                self.stdout.write(f"  Effective Support Teacher: {is_support_teacher(user)}")
                if owns and not in_group(user, TEACHER_GROUP):
                    self.stdout.write(self.style.ERROR("  MISMATCH: owns classrooms but is not in Teacher group; teacher access is revoked."))
                if support_profile and not in_group(user, SUPPORT_TEACHER_GROUP):
                    self.stdout.write(self.style.ERROR("  MISMATCH: has support profile but is not in Support Teacher group; support access is revoked."))
                self.stdout.write("")

        if not found:
            self.stdout.write(self.style.SUCCESS("No role-integrity mismatches found."))
