from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.sat.models import English_Question


CONFIG = {
    1: {
        "answers": ["The scientist's analysis of the data was very careful.", "The scientist conducted a careful analysis of the data."],
        "patterns": [r".*\banalysis\b.*\bdata\b.*"],
    },
    2: {
        "answers": ["Migratory birds travel south every autumn.", "Colorful birds migrate every winter."],
        "patterns": [],
    },
    3: {"answers": ["She walks to school every day."], "patterns": [r"she walks to school every day"]},
    4: {
        "answers": ["The train had already left before we arrived at the station.", "By the time we arrived at the station, the train had left."],
        "patterns": [r".*\btrain\b.*\bhad(?: already)? left\b.*\b(?:we )?arrived\b.*", r".*\bwe arrived\b.*\btrain had(?: already)? left\b.*"],
    },
    5: {
        "answers": ["It is going to rain.", "It's going to storm."],
        "patterns": [r"(?:it|the weather).*(?:is|'s) going to (?:rain|storm).*"],
    },
    6: {
        "answers": ["Walking to the store, I got my jacket soaked.", "While I was walking to the store, the rain soaked my jacket."],
        "patterns": [r"walking to the store,? i .*jacket.*", r"while i was walking to the store,? the rain soaked my jacket"],
    },
    7: {
        "answers": ["Although the team practiced hard, they lost the final."],
        "patterns": [r"although the team practiced hard,? they lost the final"],
    },
    8: {
        "answers": ["She said that she would finish the project the next day.", "She said she would finish the project the following day."],
        "patterns": [r"she said(?: that)? she would finish the project (?:the )?(?:next|following) day"],
    },
    9: {"answers": ["Exercising every morning is healthy."], "patterns": [r"exercising every morning is healthy"]},
    10: {
        "answers": ["She studies hard to pass the exam.", "She studies hard in order to pass the exam."],
        "patterns": [r"she studies hard (?:in order )?to pass the exam"],
    },
    11: {
        "answers": ["If it rains tomorrow, we will cancel the picnic.", "If it rains tomorrow, I will stay home."],
        "patterns": [r"if it rains tomorrow,? .+ will [a-z]+(?: .+)?"],
    },
    12: {
        "answers": ["If he had studied, he would not have failed the test."],
        "patterns": [r"if he had studied,? he would(?:n't| not) have failed the test"],
    },
    13: {"answers": ["have you?", "have you"], "patterns": [r"have you"]},
    14: {
        "answers": ["Could you tell me where the train station is?", "Could you tell me where the train station is"],
        "patterns": [r"could you tell me where the train station is"],
    },
    15: {
        "answers": ["The results will be announced by the committee on Friday.", "The results will be announced on Friday."],
        "patterns": [r"the results will be announced(?: by the committee)? on friday"],
    },
}


class Command(BaseCommand):
    help = "Configure Placement Test writing questions 1-15 for deterministic open-text grading."

    def add_arguments(self, parser):
        parser.add_argument("--test", required=True, help="Exact unique test name. Avoid reusing the SAT Placement Test name.")
        parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag the command is a dry run.")

    @transaction.atomic
    def handle(self, *args, **options):
        test_name = options["test"]
        qs = English_Question.objects.filter(test__name__iexact=test_name, number__in=CONFIG).order_by("number", "id")
        found = list(qs)
        if not found:
            raise CommandError(f"No English questions 1-15 found for test {test_name!r}.")
        by_number = {}
        duplicates = []
        for q in found:
            if q.number in by_number:
                duplicates.append(q.number)
            else:
                by_number[q.number] = q
        missing = sorted(set(CONFIG) - set(by_number))
        if duplicates:
            raise CommandError(f"Duplicate English question numbers found: {sorted(set(duplicates))}. Fix numbering first.")
        if missing:
            self.stdout.write(self.style.WARNING(f"Missing question numbers: {missing}"))

        for number, question in sorted(by_number.items()):
            item = CONFIG[number]
            self.stdout.write(f"Q{number}: open_text; {len(item['answers'])} accepted answers; {len(item['patterns'])} patterns")
            if options["apply"]:
                question.response_type = "open_text"
                question.answer = item["answers"][0]
                question.accepted_answers = "\n".join(item["answers"])
                question.answer_patterns = "\n".join(item["patterns"])
                question.save(update_fields=["response_type", "answer", "accepted_answers", "answer_patterns", "updated_at"])

        if options["apply"]:
            self.stdout.write(self.style.SUCCESS(f"Configured {len(by_number)} questions."))
        else:
            self.stdout.write(self.style.WARNING("Dry run only. Add --apply to save."))
        self.stdout.write(self.style.WARNING(
            "Q2 asks for adjective identification and underlining, and Q5/Q11 allow many valid sentences. "
            "Deterministic rules cannot fully judge those tasks. Review their accepted variants after pilot testing."
        ))
