from django.utils.safestring import mark_safe

ENGLISH_TEXT_FIELDS = ("passage", "question", "a", "b", "c", "d", "explained")

_FORMAT_COMMANDS = {
    "textit": ("<em>", "</em>"),
    "emph": ("<em>", "</em>"),
    "underline": ("<u>", "</u>"),
    # In reading passages, \text{...} is normally just a wrapper around text.
    "text": ("", ""),
}


def _find_matching_brace(value, open_index):
    """Return the matching } index for value[open_index] == {, or -1."""
    depth = 0
    i = open_index
    while i < len(value):
        ch = value[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _find_matching_inline_math(value, open_index):
    r"""Return index of the matching \) for value[open_index:open_index+2] == \(."""
    depth = 1
    i = open_index + 2
    while i < len(value) - 1:
        token = value[i:i + 2]
        if token == r"\(":
            depth += 1
            i += 2
            continue
        if token == r"\)":
            depth -= 1
            if depth == 0:
                return i
            i += 2
            continue
        i += 1
    return -1


def _read_command(value, slash_index):
    i = slash_index + 1
    start = i
    while i < len(value) and value[i].isalpha():
        i += 1
    if i == start:
        return None, slash_index + 1
    return value[start:i], i


def _convert_latex_text_commands(value):
    r"""
    Convert only text-formatting LaTeX commands to HTML.

    Handles nested cases like:
      \underline{whose novel \(\textit{Primeval and Other Times}\) resembles ...}
      \text{\underline{whose novel ...}}

    Unknown LaTeX commands are left untouched, so real math is not destroyed.
    """
    output = []
    i = 0
    converted_any = False

    while i < len(value):
        if value.startswith(r"\(", i):
            close = _find_matching_inline_math(value, i)
            if close == -1:
                output.append(value[i:])
                break

            inner = value[i + 2:close]
            converted_inner, inner_changed = _convert_latex_text_commands(inner)
            if inner_changed:
                output.append(converted_inner)
                converted_any = True
            else:
                output.append(value[i:close + 2])
            i = close + 2
            continue

        if value[i] == "\\":
            command, after_command = _read_command(value, i)
            if command in _FORMAT_COMMANDS:
                while after_command < len(value) and value[after_command].isspace():
                    after_command += 1
                if after_command < len(value) and value[after_command] == "{":
                    close_brace = _find_matching_brace(value, after_command)
                    if close_brace != -1:
                        inner = value[after_command + 1:close_brace]
                        converted_inner, _ = _convert_latex_text_commands(inner)
                        prefix, suffix = _FORMAT_COMMANDS[command]
                        output.append(f"{prefix}{converted_inner}{suffix}")
                        converted_any = True
                        i = close_brace + 1
                        continue

            output.append(value[i])
            i += 1
            continue

        output.append(value[i])
        i += 1

    return "".join(output), converted_any


def convert_reading_latex_to_html(value):
    if not value:
        return value

    result, _ = _convert_latex_text_commands(str(value))
    return mark_safe(result)


def format_english_question_for_display(question):
    if not question:
        return question
    for field_name in ENGLISH_TEXT_FIELDS:
        if hasattr(question, field_name):
            current_value = getattr(question, field_name)
            if current_value:
                setattr(question, field_name, convert_reading_latex_to_html(current_value))
    return question


def format_english_questions_for_display(questions):
    formatted = list(questions)
    for question in formatted:
        format_english_question_for_display(question)
    return formatted
