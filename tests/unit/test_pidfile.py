#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from pathlib import Path

from comicarr.app.core.pidfile import check_stale_pidfile


def test_pidfile_check_is_platform_safe_and_handles_nul_separated_cmdline(tmp_path):
    pidfile = tmp_path / "comicarr.pid"
    pidfile.write_text("123")
    proc_root = tmp_path / "proc"
    cmdline = proc_root / "123" / "cmdline"
    cmdline.parent.mkdir(parents=True)
    cmdline.write_bytes(b"/usr/bin/python3\x00Comicarr.py\x00")

    assert check_stale_pidfile(pidfile, platform_name="darwin", proc_root=proc_root) is False
    assert check_stale_pidfile(pidfile, platform_name="linux", proc_root=tmp_path / "missing-proc") is False
    assert check_stale_pidfile(pidfile, platform_name="linux", proc_root=proc_root) is False


def test_pidfile_check_detects_bad_pid_and_non_python_process(tmp_path):
    pidfile = tmp_path / "comicarr.pid"
    proc_root = tmp_path / "proc"
    proc_root.mkdir()

    pidfile.write_text("not-a-pid")
    assert check_stale_pidfile(pidfile, platform_name="linux", proc_root=proc_root) is True

    pidfile.write_text("456")
    cmdline = proc_root / "456" / "cmdline"
    cmdline.parent.mkdir(parents=True)
    cmdline.write_text("/usr/bin/other\x00")

    assert check_stale_pidfile(pidfile, platform_name="linux", proc_root=proc_root) is True


def test_pidfile_check_keeps_pidfile_when_process_inspection_fails(tmp_path, monkeypatch):
    pidfile = tmp_path / "comicarr.pid"
    pidfile.write_text("789")
    proc_root = tmp_path / "proc"
    cmdline = proc_root / "789" / "cmdline"
    cmdline.parent.mkdir(parents=True)
    cmdline.write_text("/usr/bin/python3")
    original_read_text = Path.read_text

    def fail_only_for_cmdline(path, *args, **kwargs):
        if path == cmdline:
            raise PermissionError("inspection denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_only_for_cmdline)

    assert check_stale_pidfile(pidfile, platform_name="linux", proc_root=proc_root) is False


def test_pidfile_check_keeps_pidfile_when_pidfile_cannot_be_read(tmp_path, monkeypatch):
    pidfile = tmp_path / "comicarr.pid"
    pidfile.write_text("789")
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    original_read_text = Path.read_text

    def fail_only_for_pidfile(path, *args, **kwargs):
        if path == pidfile:
            raise PermissionError("pidfile denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_only_for_pidfile)

    assert check_stale_pidfile(pidfile, platform_name="linux", proc_root=proc_root) is False
