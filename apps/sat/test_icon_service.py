from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from .models import Test

AUTO_ICON_MARKER = "/auto/"
AUTO_ICON_PREFIX = "auto/"
DEFAULT_TEMPLATE_RELATIVE = Path("static/assets/img/tests/57.png")
DEFAULT_FALLBACK_RELATIVE = "assets/img/tests/default.png"

_DAY_RE = re.compile(r"^\s*day\s*([0-9]{1,3})\s*$", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^\s*([0-9]{1,3})\s*$")


def extract_day_number(name: str) -> Optional[int]:
    value = str(name or "")
    match = _DAY_RE.match(value) or _NUMBER_RE.match(value)
    if not match:
        return None
    try:
        number = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 999 else None


def is_auto_test_icon(icon) -> bool:
    name = str(getattr(icon, "name", "") or "").replace("\\", "/")
    return AUTO_ICON_MARKER in f"/{name}" or "/sat/test_icons/auto/" in f"/{name}"


def _font_candidates():
    # Use common OS fonts without bundling any font files in the repository.
    return [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("/usr/share/fonts/truetype/lato/Lato-Heavy.ttf"),
        Path("/usr/share/fonts/truetype/lato/Lato-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]


def _load_font(size: int):
    for candidate in _font_candidates():
        try:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int, start_size: int = 70):
    for size in range(start_size, 19, -1):
        font = _load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width and (bbox[3] - bbox[1]) <= max_height:
            return font, bbox
    font = _load_font(20)
    return font, draw.textbbox((0, 0), text, font=font)


def _label_for_test(name: str) -> str:
    number = extract_day_number(name)
    if number is not None:
        return f"DAY {number}"
    cleaned = " ".join(str(name or "SAT TEST").strip().upper().split()) or "SAT TEST"
    # A custom icon is still preferable for long/special tests; this fallback
    # remains readable without breaking the supplied SAT visual identity.
    return cleaned[:22]


def build_default_test_icon_png(name: str) -> bytes:
    template_path = Path(settings.BASE_DIR) / DEFAULT_TEMPLATE_RELATIVE
    with Image.open(template_path) as source:
        image = source.convert("RGBA")

    draw = ImageDraw.Draw(image)
    # Right lavender panel from the supplied DAY 57 template. Repainting only
    # its safe interior preserves the original rounded corners and SAT shield.
    panel_fill = image.getpixel((210, 100))
    draw.rectangle((205, 58, 461, 161), fill=panel_fill)

    label = _label_for_test(name)
    font, bbox = _fit_font(draw, label, max_width=238, max_height=58, start_size=70)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    center_x = (191 + 466) / 2
    center_y = (36 + 185) / 2
    x = center_x - text_width / 2 - bbox[0]
    y = center_y - text_height / 2 - bbox[1]
    draw.text((x, y), label, font=font, fill=(255, 255, 255, 255))

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def ensure_default_test_icon(test: Test, *, force: bool = False) -> bool:
    """Create/regenerate the MakonBook branded icon when no custom icon exists.

    Returns True when a new image was written. Custom uploads are never
    overwritten unless `force=True` is explicitly used by trusted code.
    """
    current = getattr(test, "icon", None)
    if current and getattr(current, "name", "") and not force:
        return False

    old_name = str(getattr(current, "name", "") or "") if current else ""
    png = build_default_test_icon_png(test.name)
    slug = slugify(str(test.name or "test"))[:70] or "test"
    filename = f"{AUTO_ICON_PREFIX}{slug}.png"

    test.icon.save(filename, ContentFile(png), save=False)
    Test.objects.filter(pk=test.pk).update(icon=test.icon.name)

    if old_name and old_name != test.icon.name and is_auto_test_icon(type("Icon", (), {"name": old_name})()):
        try:
            test.icon.storage.delete(old_name)
        except Exception:
            # Storage cleanup must never make test creation/editing fail.
            pass
    return True


def regenerate_auto_test_icon(test: Test) -> bool:
    if not getattr(test, "icon", None) or not getattr(test.icon, "name", ""):
        return ensure_default_test_icon(test)
    if not is_auto_test_icon(test.icon):
        return False

    old_name = test.icon.name
    test.icon = None
    changed = ensure_default_test_icon(test, force=True)
    if changed and old_name and old_name != test.icon.name:
        try:
            test.icon.storage.delete(old_name)
        except Exception:
            pass
    return changed
