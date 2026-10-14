"""Parsed, timezone-aware timestamps for the model fields that hold one.

Discogs sends timestamps as strings in more than one shape: ISO 8601 with an
offset, the same with a space instead of ``T``, and, on inventory exports and
uploads, no offset at all. Every timestamp field parses to an aware ``datetime``
so values from any endpoint compare and sort together.

Discogs does not document the zone of a value sent without an offset, so
``NAIVE_TIMESTAMP_ZONE`` is an assumption. What it rests on, measured 2026-10-11:

- Release timestamps follow the seasons: ``-08:00`` on winter dates (352665
  ``date_added`` ``2005-01-03T23:17:26-08:00``, release 3 ``date_changed``
  ``2025-12-10T09:04:39-08:00``), ``-07:00`` on summer ones. That fits
  ``America/Los_Angeles`` but was only sampled on releases. The vendored
  reference examples are unreliable here: several winter dates there show
  ``-07:00``.
- Inventory export ``created_ts`` and ``finished_ts`` carry no offset. An export
  requested at ``14:07:34Z`` (local clock agreeing with the server's ``Date``
  header to the second) came back as ``2026-10-11T07:07:34``, i.e. UTC-7. One
  summer sample; winter behaviour is unmeasured. Inventory uploads use the same
  fields per the reference but were not measured, since an upload creates
  listings.

Other shapes in the reference: a space instead of ``T`` (``registered``,
``2011-08-30 14:21:45-07:00``), and ``-00:00`` in a test payload, which pydantic
reads as UTC. If a winter export or an upload ever disagrees, revisit the
assumption.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

from pydantic import BeforeValidator, TypeAdapter, ValidationError, ValidationInfo

logger = logging.getLogger("discogs_sdk")

# Assumed zone of a timestamp sent without an offset; see the module docstring
# for the measurements behind it.
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
