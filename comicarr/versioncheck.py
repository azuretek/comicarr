#  Copyright (C) 2012–2024 Mylar3 contributors
#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#  Originally based on Mylar3 (https://github.com/mylar3/mylar3).
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Comicarr is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Comicarr.  If not, see <http://www.gnu.org/licenses/>.

import calendar
import datetime
import os
import platform
import re
import subprocess
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

import requests
from sqlalchemy import select

import comicarr
from comicarr import db, logger
from comicarr.tables import jobhistory

# Version state is read from the runtime context by GET /api/system/version.
# The context is built once at startup from a snapshot of these globals, so a
# write that lands only on the module is invisible to the API for the life of
# the process -- which is why the scheduled version check never moved the
# "update available" banner. Route every write through here instead.
_VERSION_FIELDS = {
    "current_version": "CURRENT_VERSION",
    "current_version_name": "CURRENT_VERSION_NAME",
    "current_release_name": "CURRENT_RELEASE_NAME",
    "current_branch": "CURRENT_BRANCH",
    "latest_version": "LATEST_VERSION",
    "update_state": "UPDATE_STATE",
    "update_reason": "UPDATE_REASON",
    "install_type": "INSTALL_TYPE",
    "update_value": "UPDATE_VALUE",
}

# Constant release endpoint — never interpolated with GIT_USER (#470 / #456).
_GITHUB_RELEASES_LATEST = "https://api.github.com/repos/frankieramirez/comicarr/releases/latest"

# GitHub update-check calls must not hang indefinitely on a dropped SYN
# (air-gapped / firewalled installs). Bound from issue #446: 10s connect, 10s read.
_GITHUB_REQUEST_TIMEOUT = (10, 10)


def _set_version_state(**fields):
    """Write version state once and project it to legacy callers.

    Falls back to a plain module write before the runtime exists (versionload
    runs ahead of the factory) and after it is disposed.
    """
    from comicarr.app.core.runtime import get_runtime_if_initialized, set_runtime_field

    ctx = get_runtime_if_initialized()
    if ctx is not None and ctx.disposed:
        ctx = None

    for field, value in fields.items():
        legacy_name = _VERSION_FIELDS[field]
        if ctx is None:
            setattr(comicarr, legacy_name, value)
        else:
            set_runtime_field(ctx, field, value)


def _get_version_state(field):
    """Read version state from wherever _set_version_state last wrote it."""
    from comicarr.app.core.runtime import get_runtime_if_initialized

    ctx = get_runtime_if_initialized()
    if ctx is not None and ctx.disposed:
        ctx = None

    if ctx is None:
        return getattr(comicarr, _VERSION_FIELDS[field], None)
    return getattr(ctx, field, None)


def runGit(args, ptv=None, suppress_errors=False):

    git_locations = []
    if ptv is not None:
        if ptv["git_path"] is not None:
            git_locations.append(ptv["git_path"])
    else:
        if comicarr.CONFIG.GIT_PATH is not None:
            git_locations.append(comicarr.CONFIG.GIT_PATH)

    git_locations.append("git")

    if platform.system().lower() == "darwin":
        git_locations.append("/usr/local/git/bin/git")

    output = None

    for cur_git in git_locations:
        gitworked = False

        import shlex

        cmd_list = [cur_git] + shlex.split(args)

        try:
            logger.debug("Trying to execute: %s in %s" % (cmd_list, comicarr.PROG_DIR))
            output = subprocess.run(cmd_list, text=True, capture_output=True, cwd=comicarr.PROG_DIR)
            logger.debug("Git output: %s" % output)
            gitworked = True
        except Exception as e:
            if not suppress_errors:
                logger.error("Command %s didn't work [%s]" % (cmd_list, e))
            gitworked = False
            output = None
            continue
        else:
            if all([output.stderr is not None, output.stderr != "", output.returncode > 0]):
                if not suppress_errors:
                    logger.error("Encountered error: %s" % output.stderr)
                gitworked = False

        if all(
            [
                gitworked is True,
                "not found" in output.stdout,
                "not recognized as an internal or external command" in output.stdout,
            ]
        ):
            if not suppress_errors:
                logger.error("[%s] Unable to find git with command: %s" % (output.stdout, cmd))
            output = None
            gitworked = False
        elif ("fatal:" in output.stdout) or ("fatal:" in output.stderr):
            if not suppress_errors:
                logger.error("Error: %s" % output.stderr)
                logger.error("Git returned bad info. Are you sure this is a git installation? [%s]" % output.stdout)
            output = None
            gitworked = False
        elif gitworked:
            output = output.stdout
            break

    return output


def getVersion(ptv):
    current_version = None
    current_version_name = None
    current_release_name = None

    if ptv["git_branch"] is not None and ptv["git_branch"].startswith("win32build"):
        _set_version_state(install_type="win")

        # Don't have a way to update exe yet, but don't want to set VERSION to None
        return {
            "current_version": "Windows Install",
            "current_version_name": "None",
            "branch": "None",
            "current_release_name": current_release_name,
        }

    elif os.path.isdir(os.path.join(comicarr.PROG_DIR, ".git")):
        _set_version_state(install_type="git")
        # Try exact tag match first, then get branch name separately
        output = runGit("describe --exact-match --tags", ptv, suppress_errors=True)
        if output:
            branch_output = runGit("rev-parse --abbrev-ref HEAD", ptv)
            if branch_output:
                output = output.strip() + "\n" + branch_output.strip() + "\n"
            else:
                output = None

        if not output:
            # Not on a tag — get commit hash and branch
            output = runGit("rev-parse HEAD --abbrev-ref HEAD", ptv)
            if not output:
                logger.error("Couldn't find latest installed version.")
                cur_commit_hash = None
                cur_branch = ptv["git_branch"]
        # branch_history, err = runGit("log --oneline --pretty=format:'%h - %ar - %s' -n 5")
        # bh = []
        # print ("branch_history: " + branch_history)
        # bh.append(branch_history.split('\n'))
        # print ("bh1: " + bh[0])

        if output is not None:
            opp = output.find("\n")
            cur_commit_hash = output[:opp]
            cur_branch = output[opp : output.find("\n", opp + 1)].strip()

            if cur_commit_hash.startswith("v") and ptv.get("check_github", True):
                url2 = "https://api.github.com/repos/%s/comicarr/tags" % (ptv["git_user"])
                try:
                    response = requests.get(url2, verify=True, auth=ptv["git_token"], timeout=_GITHUB_REQUEST_TIMEOUT)
                    git = response.json()
                except Exception as e:
                    logger.warn("[ERROR] %s" % e)
                    pass
                else:
                    if git[0]["name"] is not None:
                        for x in git:
                            if x["name"] == output[:opp]:
                                current_version_name = x["name"]
                                cur_commit_hash = x["commit"]["sha"]
                                break
                        logger.info("version_name: %s" % current_version_name)
                        url3 = "https://api.github.com/repos/%s/comicarr/releases/tags/%s" % (
                            ptv["git_user"],
                            current_version_name,
                        )
                        # logger.fdebug('url3: %s' % url3)
                        try:
                            repochk = requests.get(
                                url3, verify=True, auth=ptv["git_token"], timeout=_GITHUB_REQUEST_TIMEOUT
                            )
                            repo_resp = repochk.json()
                            # logger.fdebug('repo_resp: %s' % repo_resp)
                            current_release_name = repo_resp["name"]
                        except Exception:
                            pass

        logger.info("cur_commit_hash: %s" % cur_commit_hash)
        logger.info("cur_branch: %s" % cur_branch)

        if (
            cur_commit_hash is not None
            and not re.match("^[a-z0-9]+$", cur_commit_hash)
            and current_version_name is None
        ):
            logger.error("Output does not look like a hash, not using it")
            cur_commit_hash = None

        if ptv["git_branch"] == cur_branch:
            branch = ptv["git_branch"]

        if cur_commit_hash is None:
            branch = None
        else:
            branch = None
            branch_name = runGit("branch --contains %s" % cur_commit_hash, ptv)
            if not branch_name:
                logger.warn("Could not retrieve branch name [%s] from git. Defaulting to Master." % branch)
                branch = "master"
            else:
                for line in branch_name.split("\n"):
                    if "*" in line:
                        branch = re.sub("[\\*\n]", "", line).strip()
                        break

        if not branch and ptv["git_branch"]:
            logger.warn(
                "Unable to retrieve branch name [%s] from git. Setting branch to configuration value of : %s"
                % (branch, ptv["git_branch"])
            )
            branch = ptv["git_branch"]
        if not branch:
            logger.warn("Could not retrieve branch name [%s] from git. Defaulting to Master." % branch)
            branch = "master"
        else:
            logger.info("Branch detected & set to : %s" % branch)

        return {
            "current_version": cur_commit_hash,
            "current_version_name": current_version_name,
            "branch": branch,
            "current_release_name": current_release_name,
        }

    else:
        d_path = "/proc/self/cgroup"
        if (
            os.path.exists("/.dockerenv")
            or "KUBERNETES_SERVICE_HOST" in os.environ
            or os.path.isfile(d_path)
            and any("docker" in line for line in open(d_path))
        ):
            logger.info("[DOCKER-AWARE] Docker installation detected.")
            _set_version_state(install_type="docker")
            if any([comicarr.CONFIG.DESTINATION_DIR is None, comicarr.CONFIG.DESTINATION_DIR == ""]):
                logger.info("[DOCKER-AWARE] Setting default comic location path to /comics")
                comicarr.CONFIG.DESTINATION_DIR = "/comics"
        else:
            logger.info("Not a Docker installation.")
            _set_version_state(install_type="source")

        # current_version = None
        branch = None

        version_file = os.path.join(comicarr.PROG_DIR, ".LAST_RELEASE")
        if current_version is None:
            try:
                if not os.path.isfile(version_file):
                    current_version = None
                else:
                    # Check if .LAST_RELEASE has unexpanded export-subst placeholders
                    # (happens when installed via git clone or Docker COPY instead of git archive)
                    with open(version_file, "r") as f:
                        raw = f.read()
                    if "$Format:" in raw or "%H" in raw:
                        logger.info("[LAST_RELEASE] File contains unexpanded git export-subst placeholders, skipping")
                    else:
                        cnt = 0
                        for i in raw.splitlines():
                            logger.info("i: %s" % (i))
                            i.split()
                            if cnt == 0:
                                if i.find(">") != -1:
                                    i_clean = i[i.find(">") + 1 :]
                                    if "," in i_clean:
                                        find_clean = i_clean.find(",")
                                        mrclean = i_clean[:find_clean].strip()
                                    else:
                                        mrclean = re.sub(r"[\)\(\>]", "", i_clean).strip()
                                    branch = mrclean
                                    logger.info("[LAST_RELEASE] Branch: %s" % branch)
                                if "tag" in i:
                                    i_clean = i.find("tag")
                                    mrclean = re.sub("tag: ", "", re.sub(r"[\(\)]", "", i[i_clean:])).strip()
                                    current_version_name = mrclean
                                    logger.info("[LAST_RELEASE] Version: %s" % current_version_name)
                                elif i[1] == "(":
                                    branch = re.sub(r"[\(\)]", "", i).strip()
                                    logger.info("[LAST_RELEASE] Branch: %s" % branch)
                            elif cnt == 1:
                                current_version = i.strip()
                                logger.info("[LAST_RELEASE] Commit: %s" % "".join(current_version))
                            elif cnt == 2:
                                current_release_name = i.strip()
                                logger.info("[LAST_RELEASE] Release Name: %s" % "".join(current_release_name))
                            cnt += 1

            except Exception as e:
                logger.error("error: %s" % e)

        if current_version_name is not None and current_release_name is None and branch == "master":
            # only master has tags - so if not master, no need to check at all.
            url2 = "https://api.github.com/repos/%s/comicarr/releases/tags/%s" % (ptv["git_user"], current_version_name)
            try:
                response = requests.get(
                    url2, verify=True, auth=comicarr.CONFIG.GIT_TOKEN, timeout=_GITHUB_REQUEST_TIMEOUT
                )
                git = response.json()
                current_release_name = git["name"]
            except Exception:
                pass
            else:
                if os.path.isfile(version_file):
                    # write the name to the .LAST_RELEASE so we don't have to poll for it
                    logger.fdebug("this would have been written to the .LAST_RELEASE file: %s" % (current_release_name))
                    try:
                        with open(version_file, "a") as wf:
                            wf.write("%s" % current_release_name)
                    except Exception:
                        pass

        if current_version:
            if comicarr.CONFIG.GIT_BRANCH:
                logger.info("Branch detected & set to : " + ptv["git_branch"])
                return {
                    "current_version": current_version,
                    "current_version_name": current_version_name,
                    "branch": ptv["git_branch"],
                    "current_release_name": current_release_name,
                }
            else:
                if branch:
                    logger.info("Branch detected & set to : " + branch)
                else:
                    branch = "master"
                    logger.warn(
                        "No branch specified within config - could not poll version from comicarr. Defaulting to %s"
                        % branch
                    )
                return {
                    "current_version": current_version,
                    "current_version_name": current_version_name,
                    "branch": branch,
                    "current_release_name": current_release_name,
                }
        else:
            if comicarr.CONFIG.GIT_BRANCH:
                logger.info("Branch detected & set to : " + ptv["git_branch"])
                return {
                    "current_version": current_version,
                    "current_version_name": current_version_name,
                    "branch": ptv["git_branch"],
                    "current_release_name": current_release_name,
                }
            else:
                logger.warn("No branch specified within config - will attempt to poll version from comicarr")
                try:
                    branch = version.COMICARR_VERSION
                    logger.info("Branch detected & set to : " + branch)
                except:
                    branch = "master"
                    logger.info(
                        "Unable to detect branch properly - set branch in config.ini, currently defaulting to : "
                        + branch
                    )
                return {
                    "current_version": current_version,
                    "current_version_name": current_version_name,
                    "branch": branch,
                    "current_release_name": current_release_name,
                }

            logger.warn("Unable to determine which commit is currently being run. Defaulting to Master branch.")


def get_release_version():
    """Local Changesets release semver. Thin wrapper for testability."""
    from comicarr.app.system.service import get_release_version as _get

    return _get()


def _strip_leading_v(tag_name):
    """Strip a single leading ``v`` / ``V`` from a GitHub release tag."""
    if not tag_name or not isinstance(tag_name, str):
        return tag_name
    if tag_name[:1] in ("v", "V"):
        return tag_name[1:]
    return tag_name


def _parse_semver(value):
    """Return a packaging Version, or None when unparseable."""
    from packaging.version import InvalidVersion, Version

    if not value:
        return None
    try:
        return Version(str(value))
    except InvalidVersion:
        return None


def _is_rate_limited(response):
    """True when GitHub refused the request for rate-limit reasons."""
    if response is None:
        return False
    if response.status_code == 429:
        return True
    if response.status_code == 403:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None and str(remaining) == "0":
            return True
        try:
            body = response.json() if callable(getattr(response, "json", None)) else {}
        except Exception as e:
            logger.fdebug("[CHECK_GITHUB] Could not parse rate-limit body: %s" % e)
            body = {}
        message = str((body or {}).get("message", "")).lower()
        if "rate limit" in message:
            return True
    return False


def _record_unknown(reason, message, latest_version=None):
    """Publish unknown state. Never reports current on a failed check."""
    fields = {"update_state": "unknown", "update_reason": reason}
    if latest_version is not None:
        fields["latest_version"] = latest_version
    _set_version_state(**fields)
    logger.warn("[CHECK_GITHUB] %s (reason=%s)" % (message, reason))
    return {
        "status": "failure",
        "update_state": "unknown",
        "update_reason": reason,
        "latest_version": _get_version_state("latest_version"),
        "release_version": get_release_version(),
        "message": message,
    }


def checkGithub(current_version=None):
    """Compare local release semver to GitHub ``releases/latest``.

    ``current_version`` is retained for call-site compatibility but is not used
    for behind-ness — identity is ``get_release_version()`` vs. the remote
    tag_name (leading ``v`` stripped once). Does not write GLOBAL_MESSAGES /
    ``check_update`` (retired by #470 / #460).
    """
    del current_version  # install SHA is not the release identity

    local = get_release_version()
    auth = getattr(comicarr.CONFIG, "GIT_TOKEN", None)

    try:
        response = requests.get(
            _GITHUB_RELEASES_LATEST,
            verify=True,
            auth=auth,
            timeout=_GITHUB_REQUEST_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except Exception as e:
        return _record_unknown("unreachable", "Could not reach GitHub releases/latest: %s" % e)

    if _is_rate_limited(response):
        return _record_unknown("rate_limited", "GitHub rate-limited the release check")

    if getattr(response, "status_code", None) != 200:
        return _record_unknown(
            "unreachable",
            "GitHub releases/latest returned HTTP %s" % getattr(response, "status_code", "?"),
        )

    try:
        payload = response.json()
        tag_name = payload.get("tag_name")
    except Exception as e:
        return _record_unknown("unreachable", "Could not parse GitHub releases/latest: %s" % e)

    latest = _strip_leading_v(tag_name)
    local_v = _parse_semver(local)
    remote_v = _parse_semver(latest)

    if local_v is None or remote_v is None:
        # Unparseable is a failed check — never current, never "never_checked".
        return _record_unknown(
            "unreachable",
            "Unparseable release version (local=%r remote=%r)" % (local, latest),
            latest_version=latest,
        )

    # Ahead of latest collapses to current — no "N commits ahead" language.
    if local_v < remote_v:
        state = "behind"
        message = "New version is available: %s (installed %s)" % (latest, local)
    else:
        state = "current"
        message = "Comicarr is up to date (%s)" % local

    _set_version_state(latest_version=latest, update_state=state, update_reason=None)
    logger.info("[CHECK_GITHUB] %s" % message)
    return {
        "status": "success",
        "update_state": state,
        "update_reason": None,
        "latest_version": latest,
        "release_version": local,
        "message": message,
    }


def update():

    if comicarr.INSTALL_TYPE == "win":
        logger.info("Windows .exe updating not supported yet.")
        pass

    elif comicarr.INSTALL_TYPE == "git":
        output = runGit("pull origin " + comicarr.CONFIG.GIT_BRANCH)

        if output is None:
            logger.error("Couldn't download latest version")
            return

        for line in output.split("\n"):
            if "Already up-to-date." in line:
                logger.info("No update available, not updating")
                logger.info("Output: " + str(output))
            elif line.endswith("Aborting."):
                logger.error("Unable to update from git: " + line)
                logger.info("Output: " + str(output))

    elif comicarr.INSTALL_TYPE == "docker":
        logger.info(
            "Docker updates via it's own mechanics. Updating docker via Comicarr GUI not supported at this time."
        )

    else:
        tar_download_url = "https://github.com/%s/comicarr/tarball/%s" % (
            comicarr.CONFIG.GIT_USER,
            comicarr.CONFIG.GIT_BRANCH,
        )
        update_dir = os.path.join(comicarr.PROG_DIR, "update")

        try:
            logger.info("Downloading update from: " + tar_download_url)
            response = requests.get(tar_download_url, verify=True, stream=True)
        except (IOError, urllib.error.URLError):
            logger.error("Unable to retrieve new version from " + tar_download_url + ", can't update")
            return

        # try sanitizing the name here...
        download_name = comicarr.CONFIG.GIT_BRANCH + "-github"  # data.geturl().split('/')[-1].split('?')[0]
        tar_download_path = os.path.join(comicarr.PROG_DIR, download_name)

        # Save tar to disk
        with open(tar_download_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()

        # Extract the tar to update folder
        logger.info("Extracting file" + tar_download_path)
        tar = tarfile.open(tar_download_path)
        tar.extractall(update_dir)
        tar.close()

        # Delete the tar.gz
        logger.info("Deleting file" + tar_download_path)
        os.remove(tar_download_path)

        # Find update dir name
        update_dir_contents = [x for x in os.listdir(update_dir) if os.path.isdir(os.path.join(update_dir, x))]
        if len(update_dir_contents) != 1:
            logger.error("Invalid update data, update failed: " + str(update_dir_contents))
            return
        content_dir = os.path.join(update_dir, update_dir_contents[0])

        # walk temp folder and move files to main folder
        for dirname, _dirnames, filenames in os.walk(content_dir):
            dirname = dirname[len(content_dir) + 1 :]
            for curfile in filenames:
                old_path = os.path.join(content_dir, dirname, curfile)
                new_path = os.path.join(comicarr.PROG_DIR, dirname, curfile)

                if os.path.isfile(new_path):
                    os.remove(new_path)
                os.renames(old_path, new_path)


def versionload(cli_values=None, carepackage_call=False):
    if cli_values:
        pass_thru_vals = cli_values
    else:
        pass_thru_vals = {
            "git_branch": comicarr.CONFIG.GIT_BRANCH,
            "git_user": comicarr.CONFIG.GIT_USER,
            "git_token": comicarr.CONFIG.GIT_TOKEN,
            "check_github": comicarr.CONFIG.CHECK_GITHUB,
            "git_path": comicarr.CONFIG.GIT_PATH,
        }

    version_info = getVersion(pass_thru_vals)
    logger.fdebug("version_info: %s" % (version_info,))
    _set_version_state(
        current_version=version_info["current_version"],
        current_version_name=version_info["current_version_name"],
        current_release_name=version_info["current_release_name"],
        update_state="unknown",
        update_reason="never_checked",
        latest_version=None,
    )

    if cli_values or carepackage_call is True:
        # if cli_values exist, it's from maintenance mode CLI switch, just return now
        return {
            "current_branch": version_info["branch"],
            "current_version": version_info["current_version"],
            "current_version_name": version_info["current_version_name"],
            "current_release_name": version_info["current_release_name"],
            "install_type": comicarr.INSTALL_TYPE,
        }

    comicarr.CONFIG.GIT_BRANCH = version_info["branch"]
    # Nothing wrote this before, so /api/system/version always reported null.
    _set_version_state(current_branch=version_info["branch"])

    if comicarr.CURRENT_VERSION is not None:
        hash = comicarr.CURRENT_VERSION[:7]
    else:
        hash = "unknown"

    if comicarr.CONFIG.GIT_BRANCH == "master":
        vers = "M"
    elif comicarr.CONFIG.GIT_BRANCH == "python3-dev":
        vers = "D"
    else:
        vers = "NONE"

    comicarr.USER_AGENT = "Comicarr/" + str(hash) + "(" + vers + ") +https://github.com/frankieramirez/comicarr/"

    logger.info("Version information: %s [%s]" % (comicarr.CONFIG.GIT_BRANCH, comicarr.CURRENT_VERSION))

    # When check is on, run on startup for every install type (including docker).
    # CHECK_GITHUB_ON_STARTUP and the docker gate are retired (#470 / #446).
    if comicarr.CONFIG.CHECK_GITHUB:
        stmt = select(jobhistory.c.prev_run_timestamp).where(jobhistory.c.JobName == "Check Version")
        with db.get_engine().connect() as conn:
            chk_last = conn.execute(stmt).mappings().fetchone()
        prev_run = False
        if chk_last:
            if chk_last["prev_run_timestamp"] is not None:
                rd = datetime.datetime.utcfromtimestamp(chk_last["prev_run_timestamp"])
                rd_mins = rd + datetime.timedelta(seconds=900)
                rd_now = datetime.datetime.utcfromtimestamp(time.time())
                if calendar.timegm(rd_mins.utctimetuple()) > calendar.timegm(rd_now.utctimetuple()):
                    prev_run = True
                    logger.info("[CHECK_GITHUB] Version check ran  < 15 minutes ago. Not running.")

        if prev_run is False:
            try:
                ac = comicarr.versioncheckit.CheckVersion()
                ac.run(scheduled_job=False)
            except Exception as e:
                logger.warn("[CHECK_GITHUB] Startup release check failed: %s" % e)
