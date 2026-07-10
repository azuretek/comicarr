#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Canonical, reconstructable commands for the direct-download worker."""

import datetime
import json
from dataclasses import dataclass
from typing import Any, Mapping


class DDLCommandError(ValueError):
    """Raised when a direct-download request cannot be executed safely."""


_GETCOMICS_LINK_TYPES = {
    "GC-Main",
    "GC-Mirror",
    "GC-Mega",
    "GC-Media",
    "GC-Pixel",
}
_EXTERNAL_LINK_TYPES = {"Mega", "Mega Link", "GC-Mega"}
_LINK_TYPE_ALIASES = {"GC_Mirror": "GC-Mirror"}


def _required_text(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key)
    if value is None or not str(value).strip():
        raise DDLCommandError("Missing required DDL field: %s" % key)
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_nonnegative_int(value: Any, key: str) -> int | None:
    if value in (None, "") or (isinstance(value, str) and value.strip().lower() in {"none", "null"}):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError) as e:
        raise DDLCommandError("Invalid integer DDL field: %s" % key) from e
    if normalized < 0:
        raise DDLCommandError("DDL field must be non-negative: %s" % key)
    return normalized


def _bool_value(value: Any, key: str) -> bool:
    if isinstance(value, str):
        if value.strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if value.strip().lower() in {"", "0", "false", "no", "off", "none"}:
            return False
        raise DDLCommandError("Invalid boolean DDL field: %s" % key)
    return bool(value)


def _json_value(value: Any, key: str) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            raise DDLCommandError("Invalid persisted JSON DDL field: %s" % key) from e
    try:
        json.dumps(value)
    except (TypeError, ValueError) as e:
        raise DDLCommandError("DDL field is not JSON serializable: %s" % key) from e
    return value


@dataclass(frozen=True)
class DDLCommand:
    """The complete input contract consumed by ``ddl_downloader``."""

    id: str
    link: str
    site: str
    series: str
    year: str | None
    size: str | None
    comicid: str
    issueid: str
    oneoff: bool
    link_type: str
    filename: str | None
    mainlink: str | None
    comicinfo: list[dict[str, Any]] | None
    packinfo: dict[str, Any] | None
    remote_filesize: int
    resume: int | None
    issues: str | None
    pack: bool

    @classmethod
    def from_mapping(cls, raw_values: Mapping[str, Any]) -> "DDLCommand":
        if not isinstance(raw_values, Mapping):
            raise DDLCommandError("DDL command must be an object")

        values = {str(key).lower(): value for key, value in raw_values.items()}
        raw_link_type = _required_text(values, "link_type")
        link_type = _LINK_TYPE_ALIASES.get(raw_link_type, raw_link_type)
        site = _required_text(values, "site")
        if site == "DDL(GetComics)":
            if link_type not in _GETCOMICS_LINK_TYPES:
                raise DDLCommandError("Unsupported GetComics DDL link type: %s" % link_type)
        elif site == "DDL(External)":
            if link_type not in _EXTERNAL_LINK_TYPES:
                raise DDLCommandError("Unsupported external DDL link type: %s" % link_type)
        else:
            raise DDLCommandError("Unsupported DDL site: %s" % site)

        comicinfo = _json_value(values.get("comicinfo"), "comicinfo")
        packinfo = _json_value(values.get("packinfo"), "packinfo")
        if comicinfo is not None:
            if not isinstance(comicinfo, list) or any(not isinstance(entry, Mapping) for entry in comicinfo):
                raise DDLCommandError("Invalid DDL field: comicinfo must be a list of objects")
            comicinfo = [dict(entry) for entry in comicinfo]
        if packinfo is not None:
            if not isinstance(packinfo, Mapping):
                raise DDLCommandError("Invalid DDL field: packinfo must be an object")
            packinfo = dict(packinfo)
        mainlink = _optional_text(values.get("mainlink"))
        filename = _optional_text(values.get("filename"))
        if site == "DDL(GetComics)":
            if mainlink is None:
                raise DDLCommandError("Missing required DDL field: mainlink")
            if not isinstance(comicinfo, list) or not comicinfo:
                raise DDLCommandError("Missing required DDL field: comicinfo")
        elif filename is None:
            raise DDLCommandError("Missing required DDL field: filename")

        remote_filesize = _optional_nonnegative_int(values.get("remote_filesize"), "remote_filesize")
        return cls(
            id=_required_text(values, "id"),
            link=_required_text(values, "link"),
            site=site,
            series=_required_text(values, "series"),
            year=_optional_text(values.get("year")),
            size=_optional_text(values.get("size")),
            comicid=_required_text(values, "comicid"),
            issueid=_required_text(values, "issueid"),
            oneoff=_bool_value(values.get("oneoff", False), "oneoff"),
            link_type=link_type,
            filename=filename,
            mainlink=mainlink,
            comicinfo=comicinfo,
            packinfo=packinfo,
            remote_filesize=remote_filesize or 0,
            resume=_optional_nonnegative_int(values.get("resume"), "resume"),
            issues=_optional_text(values.get("issues")),
            pack=_bool_value(values.get("pack", False), "pack"),
        )

    def to_queue_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "link": self.link,
            "site": self.site,
            "series": self.series,
            "year": self.year,
            "size": self.size,
            "comicid": self.comicid,
            "issueid": self.issueid,
            "oneoff": self.oneoff,
            "link_type": self.link_type,
            "filename": self.filename,
            "mainlink": self.mainlink,
            "comicinfo": self.comicinfo,
            "packinfo": self.packinfo,
            "remote_filesize": self.remote_filesize,
            "resume": self.resume,
            "issues": self.issues,
            "pack": self.pack,
        }

    def to_persisted_values(self, *, status: str = "Queued") -> dict[str, Any]:
        return {
            "series": self.series,
            "year": self.year,
            "filename": self.filename,
            "size": self.size,
            "issueid": self.issueid,
            "comicid": self.comicid,
            "link": self.link,
            "status": status,
            "remote_filesize": str(self.remote_filesize),
            "updated_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "mainlink": self.mainlink,
            "issues": self.issues,
            "site": self.site,
            "pack": int(self.pack),
            "link_type": self.link_type,
            "oneoff": int(self.oneoff),
            "resume": self.resume,
            "comicinfo": json.dumps(self.comicinfo) if self.comicinfo is not None else None,
            "packinfo": json.dumps(self.packinfo) if self.packinfo is not None else None,
        }
