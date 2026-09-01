#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Validated post-processing commands and symlink-safe directory walks."""

import os
from pathlib import Path, PurePath

import comicarr


class PostProcessCommandError(ValueError):
    """A post-processing command cannot be proven safe to execute."""


_ROOT_CONFIG_KEYS = (
    "DDL_LOCATION",
    "SAB_DIRECTORY",
    "NZBGET_DIRECTORY",
    "RTORRENT_DIRECTORY",
    "DELUGE_DOWNLOAD_DIRECTORY",
    "QBITTORRENT_FOLDER",
    "LOCAL_WATCHDIR",
    "CHECK_FOLDER",
    "MANUAL_PP_FOLDER",
)


def configured_roots(config=None):
    config = config if config is not None else getattr(comicarr, "CONFIG", None)
    roots = []
    for key in _ROOT_CONFIG_KEYS:
        value = getattr(config, key, None) if config is not None else None
        if value and str(value).strip().lower() != "none":
            roots.append(Path(str(value)).expanduser())
    return roots


def _contains(root, candidate):
    return candidate.is_relative_to(root)


def _canonical_path(value, label):
    if value is None or not str(value).strip():
        raise PostProcessCommandError("%s is required" % label)
    raw = str(value).strip()
    if "\x00" in raw or "\\" in raw:
        raise PostProcessCommandError("%s contains an unsafe path separator" % label)
    if ".." in PurePath(raw).parts:
        raise PostProcessCommandError("%s contains traversal" % label)
    return Path(raw).expanduser().resolve(strict=False)


def validate_mapped_path(path, roots=None, require_exists=True):
    """Canonicalize a local path and prove containment under an allowed root."""
    candidate = _canonical_path(path, "nzb_folder")
    if require_exists and not candidate.exists():
        raise PostProcessCommandError("nzb_folder does not exist")
    allowed = [_canonical_path(root, "post-processing root") for root in (roots or configured_roots())]
    if not allowed:
        raise PostProcessCommandError("no post-processing route root is configured")
    if not any(_contains(root, candidate) for root in allowed):
        raise PostProcessCommandError("nzb_folder is outside configured post-processing roots")
    return candidate


def _validate_basename(value):
    if value is None or not str(value).strip():
        raise PostProcessCommandError("nzb_name is required")
    name = str(value).strip()
    if len(name) > 1024:
        raise PostProcessCommandError("nzb_name is too long")
    if "\x00" in name or "\\" in name or "/" in name:
        raise PostProcessCommandError("nzb_name must be a basename")
    if Path(name).is_absolute() or name in {".", ".."} or ".." in PurePath(name).parts:
        raise PostProcessCommandError("nzb_name must be a safe basename")
    if os.path.basename(name) != name:
        raise PostProcessCommandError("nzb_name must be a basename")
    return name


def _is_failed_download(value):
    """True only for an explicit failed flag; anything else gets full validation."""
    return value in (True, 1, "1")


def validate_postprocess_item(item, roots=None, require_exists=True):
    """Return a normalized copy after validating the PP side-effect boundary."""
    if not isinstance(item, dict):
        raise PostProcessCommandError("post-processing command must be an object")
    command = dict(item)
    command["nzb_name"] = _validate_basename(command.get("nzb_name"))
    if _is_failed_download(command.get("failed")):
        # A failed download is never imported from this folder. It routes to
        # failed-download handling, which only needs to know the release failed
        # so it can look for a different one. Its folder legitimately sits
        # outside the post-processing roots: NZBGet leaves a FAILURE/* item
        # under InterDir, so the folder reported here is InterDir's parent
        # rather than the completed-download root.
        #
        # Requiring containment rejects the command before the failed path ever
        # runs, so the release parks in manual_review, the failure is never
        # recorded, and the identical release is grabbed again on every
        # subsequent search. Sanitize the path, but do not require containment.
        command["nzb_folder"] = str(_canonical_path(command.get("nzb_folder"), "nzb_folder"))
    else:
        command["nzb_folder"] = str(
            validate_mapped_path(command.get("nzb_folder"), roots=roots, require_exists=require_exists)
        )
    for key in ("failed", "apicall", "ddl", "oneoff"):
        if key in command and command[key] not in (None, True, False, 0, 1, "0", "1"):
            raise PostProcessCommandError("%s must be boolean" % key)
    for key in ("issueid", "comicid"):
        if key in command and command[key] is not None and not str(command[key]).strip():
            raise PostProcessCommandError("%s cannot be blank" % key)
    download_info = command.get("download_info")
    if download_info is not None and not isinstance(download_info, dict):
        raise PostProcessCommandError("download_info must be an object")
    release_key = command.get("journal_release_key")
    if release_key is not None:
        if not str(release_key).strip() or len(str(release_key)) > 1024 or "\x00" in str(release_key):
            raise PostProcessCommandError("journal_release_key is invalid")
        command["journal_release_key"] = str(release_key)
    return command


def safe_walk(root):
    """Walk without following links and omit every entry resolving outside root."""
    canonical_root = Path(root).resolve(strict=False)
    for current, dirnames, filenames in os.walk(canonical_root, followlinks=False):
        current_path = Path(current).resolve(strict=False)
        if not _contains(canonical_root, current_path):
            dirnames[:] = []
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if not (Path(current) / name).is_symlink()
            and _contains(canonical_root, (Path(current) / name).resolve(strict=False))
        ]
        safe_files = [
            name
            for name in filenames
            if not (Path(current) / name).is_symlink()
            and _contains(canonical_root, (Path(current) / name).resolve(strict=False))
        ]
        yield current, dirnames, safe_files
