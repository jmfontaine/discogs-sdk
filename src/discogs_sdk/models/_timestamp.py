"""Parsed, timezone-aware timestamps for the model fields that hold one.

Discogs sends timestamps as strings in more than one shape: ISO 8601 with an
offset, the same with a space instead of ``T``, and, on inventory exports and
uploads, no offset at all. Every timestamp field parses to an aware ``datetime``
so values from any endpoint compare and sort together.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

from pydantic import BeforeValidator, TypeAdapter, ValidationError, ValidationInfo

logger = logging.getLogger("discogs_sdk")

# Assumed zone of a timestamp sent without an offset. Discogs does not document
# it: an inventory export requested at 14:07:34Z reported 07:07:34 (UTC-7, in
# summer), and offsets the API does send switch between -07:00 and -08:00 with
# daylight saving. See "Timestamps Come in Several Shapes" in AGENTS.md.
NAIVE_TIMESTAMP_ZONE = ZoneInfo("America/Los_Angeles")

_DATETIME: TypeAdapter[datetime] = TypeAdapter(datetime)


def _parse_timestamp(value: Any, info: ValidationInfo) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = _DATETIME.validate_python(value)
    except ValidationError:
        model = info.config.get("title") if info.config else None
        logger.warning(
            "Unparseable timestamp %r in %s.%s; set to None, the original value "
            "is in .raw",
            value,
            model or "<model>",
            info.field_name,
        )
        return None
    if parsed.tzinfo is None:
        # The zone only picks the offset. Storing that offset as a fixed tzinfo
        # matches values that arrive with one, and keeps a value equal to its
        # JSON round-trip: during the hour repeated when daylight saving ends, a
        # ZoneInfo datetime compares unequal to every other zone (PEP 495). That
        # hour resolves to its first occurrence (fold=0, PDT).
        # Typed Optional for tzinfo in general; a ZoneInfo always has an offset.
        offset = cast("timedelta", NAIVE_TIMESTAMP_ZONE.utcoffset(parsed))
        parsed = parsed.replace(tzinfo=timezone(offset))
    return parsed


Timestamp = Annotated[datetime | None, BeforeValidator(_parse_timestamp)]
"""An aware ``datetime``, or ``None`` when absent, empty or unparseable.

An offset the API sends is kept as is. A value without one is taken as
``America/Los_Angeles`` wall time, an assumption measured against the API rather
than documented by Discogs, and carries the fixed offset in force at that moment
(``-08:00`` or ``-07:00``). A value that does not parse is logged as a warning on
the ``discogs_sdk`` logger and becomes ``None``; the model still loads, and the
string Discogs sent stays readable through ``model.raw``.
"""
