"""Self-update from GitHub.

The problem this solves: every user has their own copy of this folder,
installed by setup.bat and pointed at from ``%USERPROFILE%\\.audio_to_srt_path``.
Before this file existed, shipping a fix meant telling each of them to
re-download the folder and re-run setup — which in practice meant most
installs stayed on whatever version they were first given.

So: loader.pyw asks :func:`check` on every launch (off the UI thread), shows a
chip in the title bar if there is something newer, and calls :func:`install`
if the user clicks it. Nothing here ever runs without the user pressing the
button — an update that rewrites transcribe.py behind someone's back in the
middle of a job is worse than an out-of-date install.

Two things can mark a release as "newer", and the reason there are two is that
relying on either alone gets it wrong:

1. ``version.json`` at the repo root. Bump ``version`` there and you get a
   real version number and hand-written release notes in the dialog. This is
   the intended path for anything a user should read about.
2. The head commit of the branch. Push without touching version.json and
   users still get offered the update, with the commit subjects as notes.
   Without this, a forgotten version bump means a fix silently reaches nobody.

Update = download the branch zip, back up what is there, copy the new files
over the install, and refresh the copy of audio_to_srt.py that lives in
Resolve's Scripts folder. Deliberately not a ``git pull``: almost no install
is a git checkout, and the ones that are may have local edits we would rather
leave alone than merge.
"""

import io
import json
import os
import shutil
import ssl
import sys
import time
import zipfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Same reason as transcribe.py: on a network that inspects TLS, Python's
# certifi bundle has never heard of the proxy's root CA even though Windows
# trusts it, and the update check would fail with CERTIFICATE_VERIFY_FAILED on
# exactly the corporate machines this is meant to reach.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Overridable so a fork, or a test branch, needs no code edit.
OWNER = os.environ.get("SRUTILEKHA_UPDATE_OWNER", "mahadeva112")
REPO = os.environ.get("SRUTILEKHA_UPDATE_REPO", "Shrutilekha-SRT")
BRANCH = os.environ.get("SRUTILEKHA_UPDATE_BRANCH", "main")

MANIFEST_NAME = "version.json"
STATE_NAME = ".update_state.json"
BACKUP_DIR_NAME = ".update-backup"

CHECK_TIMEOUT = 12          # seconds; the window must not wait on the network
DOWNLOAD_TIMEOUT = 180
KEEP_BACKUPS = 3

# Never overwritten or deleted by an update. .env is the user's API key,
# subtitle_style.json and settings.json are their saved preferences, and logs
# are the only record of what went wrong on their machine.
PRESERVE = {
    ".env",
    "subtitle_style.json",
    "settings.json",
    STATE_NAME,
    "certs.pem",
}
PRESERVE_DIRS = {".git", "logs", ".cache", "presets", "__pycache__",
                 BACKUP_DIR_NAME, ".venv", "venv"}

# An extracted tree missing any of these is not this project — refuse rather
# than half-overwrite a working install with whatever was actually downloaded
# (a GitHub error page, an empty repo, a redirect to a login form).
REQUIRED = ("loader.pyw", "transcribe.py", "audio_to_srt.py")

RESOLVE_USER_DIR = os.path.join(
    os.environ.get("APPDATA", ""),
    "Blackmagic Design", "DaVinci Resolve", "Support", "Fusion",
    "Scripts", "Utility")
RESOLVE_SYS_DIR = os.path.join(
    os.environ.get("PROGRAMDATA", ""),
    "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts", "Utility")
RESOLVE_SCRIPT_NAME = "Srutilekha.py"


class UpdateError(Exception):
    """Anything the user can act on. loader.pyw shows str(e) verbatim in the
    dialog, so these messages are written to be read by a user, not a dev."""


# -- version numbers --------------------------------------------------------

def _parse(v):
    """"1.2.10" -> (1, 2, 10). Trailing junk ("1.2.0-beta") is dropped so a
    pre-release tag never compares as newer than the release it precedes."""
    parts = []
    for chunk in str(v or "0").strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits or 0))
    return tuple(parts)


def _newer(remote, local):
    a, b = _parse(remote), _parse(local)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def _local_manifest():
    try:
        with open(os.path.join(PROJECT_DIR, MANIFEST_NAME),
                  encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# The installed version, read from the shipped manifest so that cutting a
# release means editing one file. The literal is only the floor for an install
# old enough to predate version.json.
VERSION = str(_local_manifest().get("version") or "1.0.0")


# -- install state (which commit this folder is actually on) ----------------

def _state_path():
    return os.path.join(PROJECT_DIR, STATE_NAME)


def _read_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(**fields):
    state = _read_state()
    state.update(fields)
    try:
        tmp = _state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, _state_path())
    except Exception:
        pass                      # a lost state file costs one stale prompt


# -- HTTP -------------------------------------------------------------------

def _get(url, timeout, accept=None):
    headers = {
        # GitHub 403s a request with no User-Agent.
        "User-Agent": "Srutilekha-Updater/%s" % VERSION,
        "Accept": accept or "application/vnd.github+json",
        # raw.githubusercontent caches for ~5 min at the edge; a stale
        # manifest would hide a release that is already live.
        "Cache-Control": "no-cache",
    }
    token = os.environ.get("SRUTILEKHA_UPDATE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token   # private repo / rate limit
    req = Request(url, headers=headers)
    return urlopen(req, timeout=timeout)


def _get_json(url, timeout=CHECK_TIMEOUT):
    with _get(url, timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _friendly_net_error(err):
    if isinstance(err, HTTPError):
        if err.code == 404:
            return UpdateError(
                "GitHub returned 'not found' for %s/%s. If the repository is "
                "private, set SRUTILEKHA_UPDATE_TOKEN to a personal access "
                "token." % (OWNER, REPO))
        if err.code in (403, 429):
            return UpdateError(
                "GitHub is rate-limiting this network. Wait a few minutes and "
                "try again.")
        return UpdateError("GitHub returned HTTP %s." % err.code)
    if isinstance(err, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(err):
        return UpdateError(
            "The secure connection to GitHub could not be verified. This "
            "network inspects HTTPS traffic - run setup.bat again to install "
            "the 'truststore' package, which makes Python trust the same "
            "certificates Windows already does.")
    if isinstance(err, URLError):
        return UpdateError("Could not reach GitHub: %s" % (err.reason,))
    return UpdateError(str(err) or "The update failed.")


# -- check ------------------------------------------------------------------

def check():
    """Return an update dict, or None if there is nothing to offer.

    Never raises. This runs on every launch, and an offline machine, a blocked
    proxy or a rate-limited network must all mean "no chip", not a traceback
    into a background thread nobody reads.

    Keys, all consumed by loader.pyw: ``version``, ``released``, ``notes``
    (list of str), ``mandatory`` (bool), ``sha``, ``zip_url``.
    """
    try:
        return _check()
    except Exception:
        return None


def _check():
    head = _head_commit()
    if not head:
        return None
    sha, released, subject = head

    remote = _remote_manifest(sha)
    state = _read_state()
    local_sha = str(state.get("sha") or "")

    remote_version = str(remote.get("version") or "")
    version_newer = bool(remote_version) and _newer(remote_version, VERSION)
    commit_newer = bool(local_sha) and sha != local_sha

    if not local_sha:
        # A fresh install has no baseline commit, so the commit check is blind
        # until we record one. Recording the current head is right when the
        # folder came from a download of that head, and wrong when it came
        # from an older download that the user only launched today — that
        # second case would mark them as current on code they do not have.
        #
        # A GitHub zip stamps every file with the commit date, so the age of
        # loader.pyw is a usable stand-in for which commit this folder is. If
        # head is clearly newer than these files, do not claim to be on it;
        # offer the update instead. Slack of two days covers a download that
        # sat around before setup.bat ran.
        commit_newer = _files_predate(released)
        if not commit_newer:
            _write_state(sha=sha, version=VERSION,
                         checked=time.strftime("%Y-%m-%d %H:%M:%S"))

    if not version_newer and not commit_newer:
        return None

    if version_newer:
        label = remote_version
        notes = [str(n) for n in (remote.get("notes") or []) if str(n).strip()]
    else:
        # A push with no version bump. Say so honestly rather than inventing a
        # number: "1.0.0 (a1b2c3d)" is true, "1.0.1" would not be.
        label = "%s (%s)" % (remote_version or VERSION, sha[:7])
        notes = _recent_subjects(local_sha, sha) or ([subject] if subject else [])

    mandatory = bool(remote.get("mandatory"))
    min_version = str(remote.get("min_version") or "")
    if min_version and _newer(min_version, VERSION):
        mandatory = True

    return {
        "version": label,
        # A release can name its own date; otherwise the commit's.
        "released": str(remote.get("released") or released),
        "notes": notes,
        "mandatory": mandatory,
        "sha": sha,
        "zip_url": "https://codeload.github.com/%s/%s/zip/%s"
                   % (OWNER, REPO, sha),
    }


def _files_predate(released, slack_days=2):
    """True if the installed files look older than a commit dated ``released``.

    Conservative on every uncertainty — an unparseable date or a missing file
    returns False, i.e. "assume current", because a spurious update prompt on
    an install that is actually up to date is the worse failure."""
    if not released:
        return False
    try:
        head_at = time.mktime(time.strptime(released, "%Y-%m-%d"))
        mtime = os.path.getmtime(os.path.join(PROJECT_DIR, "loader.pyw"))
    except Exception:
        return False
    return mtime + slack_days * 86400 < head_at


def _head_commit():
    """(sha, YYYY-MM-DD, subject) for the tip of BRANCH, or None."""
    url = "https://api.github.com/repos/%s/%s/commits/%s" % (OWNER, REPO, BRANCH)
    data = _get_json(url)
    sha = str(data.get("sha") or "")
    if not sha:
        return None
    commit = data.get("commit") or {}
    date = ((commit.get("author") or {}).get("date")
            or (commit.get("committer") or {}).get("date") or "")
    lines = str(commit.get("message") or "").strip().splitlines()
    return sha, date[:10], (lines[0] if lines else "")


def _remote_manifest(sha):
    url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        OWNER, REPO, sha, MANIFEST_NAME)
    try:
        with _get(url, CHECK_TIMEOUT, accept="text/plain") as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        # No manifest in the repo yet — the commit comparison still works.
        return {}


def _recent_subjects(base_sha, head_sha, limit=6):
    """Commit subjects between the installed commit and the new one, newest
    first, to stand in for release notes when there are none."""
    if not base_sha:
        return []
    try:
        url = "https://api.github.com/repos/%s/%s/compare/%s...%s" % (
            OWNER, REPO, base_sha, head_sha)
        data = _get_json(url)
        out = []
        for c in reversed(data.get("commits") or []):
            msg = str(((c.get("commit") or {}).get("message") or "")).strip()
            first = msg.splitlines()[0] if msg else ""
            if first and first not in out:
                out.append(first)
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


# -- install ----------------------------------------------------------------

def install(info, report=None):
    """Apply ``info`` (from :func:`check`) to this install.

    Returns the path of the backup taken first. Raises :class:`UpdateError`
    with a message meant for the user on any failure. Ordering matters: the
    download is fully validated in a temp folder before a single file in the
    install is touched, so a failed or truncated download leaves the working
    version exactly as it was.
    """
    def say(msg):
        if report:
            try:
                report(msg)
            except Exception:
                pass

    if not isinstance(info, dict) or not info.get("zip_url"):
        raise UpdateError("Nothing to install.")

    if not os.access(PROJECT_DIR, os.W_OK):
        raise UpdateError(
            "No permission to write to the Srutilekha folder:\n%s"
            % PROJECT_DIR)

    staging = os.path.join(PROJECT_DIR, BACKUP_DIR_NAME,
                           "staging-%s" % time.strftime("%Y%m%d-%H%M%S"))
    try:
        say("Downloading update...")
        blob = _download(info["zip_url"], say)

        say("Extracting...")
        src = _extract(blob, staging)

        say("Backing up the current version...")
        backup = _backup()

        say("Installing files...")
        copied = _copy_tree(src, PROJECT_DIR)

        say("Updating the DaVinci Resolve menu script...")
        note = _refresh_resolve_script()

        _write_state(sha=info.get("sha", ""),
                     version=str(info.get("version") or "").split(" ")[0],
                     installed=time.strftime("%Y-%m-%d %H:%M:%S"),
                     backup=backup)
        _prune_backups()

        say("Installed %d file%s.%s" % (copied, "" if copied == 1 else "s",
                                        ("  " + note) if note else ""))
        return backup
    except UpdateError:
        raise
    except Exception as e:
        raise _friendly_net_error(e)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _download(url, say):
    """The zip, in memory. A few hundred KB of source — writing it to disk
    first would only add a second failure mode."""
    got = 0
    try:
        with _get(url, DOWNLOAD_TIMEOUT, accept="application/zip") as r:
            total = int(r.headers.get("Content-Length") or 0)
            buf = io.BytesIO()
            last = 0.0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                buf.write(chunk)
                got += len(chunk)
                now = time.time()
                if now - last > 0.25:       # don't flood the Tk event queue
                    last = now
                    if total:
                        say("Downloading update... %d%%" % (got * 100 // total))
                    else:
                        say("Downloading update... %d KB" % (got // 1024))
    except Exception as e:
        raise _friendly_net_error(e)
    if not got:
        raise UpdateError("The download was empty. Check your connection and "
                          "try again.")
    return buf.getvalue()


def _extract(blob, staging):
    """Unpack into ``staging`` and return the folder holding the project.

    GitHub wraps everything in a single ``repo-<sha>`` directory, but the name
    depends on which of GitHub's several zip endpoints served it, so find it
    rather than assume it."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise UpdateError("The downloaded file was not a valid archive. This "
                          "is usually a proxy or captive-portal page - try "
                          "again on a different network.")
    os.makedirs(staging, exist_ok=True)
    for member in zf.namelist():
        # Zip entries are attacker-controlled paths in the general case;
        # extractall has historically walked out of the target with "..".
        if os.path.isabs(member) or ".." in member.replace("\\", "/").split("/"):
            raise UpdateError("The archive contained an unsafe path and was "
                              "rejected.")
    zf.extractall(staging)

    root = staging
    entries = [e for e in os.listdir(staging)
               if os.path.isdir(os.path.join(staging, e))]
    if len(entries) == 1 and not os.path.exists(
            os.path.join(staging, REQUIRED[0])):
        root = os.path.join(staging, entries[0])

    missing = [n for n in REQUIRED if not os.path.exists(os.path.join(root, n))]
    if missing:
        raise UpdateError(
            "The download did not look like a Srutilekha release (missing %s). "
            "Nothing was changed." % ", ".join(missing))
    return root


def _copy_tree(src, dst):
    """Copy the new tree over the install, skipping what belongs to the user.

    Files the release no longer contains are left alone: a stale module is
    harmless, whereas deleting by absence would take out anything a user keeps
    in this folder."""
    copied = 0
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in PRESERVE_DIRS]
        rel = os.path.relpath(base, src)
        target_dir = dst if rel == "." else os.path.join(dst, rel)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as e:
            raise UpdateError("Could not create %s (%s)" % (target_dir, e))
        for name in files:
            if rel == "." and name in PRESERVE:
                continue
            if name.endswith((".pyc", ".pyo")):
                continue
            source = os.path.join(base, name)
            target = os.path.join(target_dir, name)
            try:
                # Via a temp name + replace: a copy interrupted halfway
                # through loader.pyw would leave a file that cannot start.
                tmp = target + ".new"
                shutil.copy2(source, tmp)
                os.replace(tmp, target)
                copied += 1
            except OSError as e:
                raise UpdateError(
                    "Could not replace %s (%s).\nIf DaVinci Resolve is "
                    "running a transcription, let it finish and try again."
                    % (name, e))
    _clear_pycache(dst)
    return copied


def _clear_pycache(root):
    """Drop compiled bytecode for the modules just replaced. Python's own
    invalidation is by size and mtime, which a copy2 preserves from the
    archive - an old .pyc can legitimately look current."""
    for base, dirs, _files in os.walk(root):
        parts = base.split(os.sep)
        if BACKUP_DIR_NAME in parts or ".git" in parts:
            dirs[:] = []
            continue
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(base, d), ignore_errors=True)
                dirs.remove(d)


def _backup():
    """Zip the current install into _backup/ and return the path.

    A zip rather than a copied folder so it cannot be mistaken for a second
    install, and so _backup/ never grows into something Resolve might scan."""
    root = os.path.join(PROJECT_DIR, BACKUP_DIR_NAME)
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, "srutilekha-%s-%s.zip"
                        % (VERSION, time.strftime("%Y%m%d-%H%M%S")))
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for base, dirs, files in os.walk(PROJECT_DIR):
                dirs[:] = [d for d in dirs if d not in PRESERVE_DIRS]
                for name in files:
                    if name.endswith((".pyc", ".pyo")):
                        continue
                    full = os.path.join(base, name)
                    zf.write(full, os.path.relpath(full, PROJECT_DIR))
    except Exception as e:
        raise UpdateError("Could not write a backup first, so nothing was "
                          "changed: %s" % e)
    return path


def _prune_backups():
    root = os.path.join(PROJECT_DIR, BACKUP_DIR_NAME)
    try:
        zips = sorted(
            (os.path.join(root, n) for n in os.listdir(root)
             if n.endswith(".zip")),
            key=os.path.getmtime, reverse=True)
        for old in zips[KEEP_BACKUPS:]:
            os.remove(old)
    except Exception:
        pass


def _refresh_resolve_script():
    """Re-copy audio_to_srt.py into Resolve's Scripts folder.

    The menu entry is a *copy*, not a link, so an update that skipped this
    would leave Resolve launching the old front end against the new backend.
    Returns a note to show the user, or "" when everything went in cleanly.
    Never fatal: the rest of the update is already applied and useful."""
    source = os.path.join(PROJECT_DIR, "audio_to_srt.py")
    if not os.path.exists(source):
        return ""

    ok = False
    if os.environ.get("APPDATA"):
        try:
            os.makedirs(RESOLVE_USER_DIR, exist_ok=True)
            shutil.copy2(source, os.path.join(RESOLVE_USER_DIR,
                                              RESOLVE_SCRIPT_NAME))
            ok = True
        except Exception:
            ok = False

    # Only refresh a machine-wide copy that already exists - creating one
    # needs admin, and setup.bat deliberately never elevates.
    sys_copy = os.path.join(RESOLVE_SYS_DIR, RESOLVE_SCRIPT_NAME)
    stale_sys = False
    if os.environ.get("PROGRAMDATA") and os.path.exists(sys_copy):
        try:
            shutil.copy2(source, sys_copy)
        except Exception:
            stale_sys = True

    if not ok:
        return ("Note: the Resolve menu script could not be updated. Run "
                "setup.bat once to finish.")
    if stale_sys:
        return ("Note: an older machine-wide copy at %s could not be replaced "
                "without admin rights - delete it when convenient." % sys_copy)
    return ""


# -- manual use -------------------------------------------------------------

def _main(argv):
    """``python updater.py`` checks; ``python updater.py --install`` applies.

    For a machine where the GUI will not start - the one case where an update
    is most needed and least reachable through the button.
    """
    print("Srutilekha %s  (%s/%s @ %s)" % (VERSION, OWNER, REPO, BRANCH))
    print("Folder: %s" % PROJECT_DIR)
    try:
        info = _check()
    except Exception as e:
        print("Check failed: %s" % _friendly_net_error(e))
        return 2
    if not info:
        print("Up to date.")
        return 0
    print("Update available: %s%s" % (
        info["version"],
        "  (required)" if info["mandatory"] else ""))
    for line in info["notes"]:
        print("  - %s" % line)
    if "--install" not in argv:
        print("\nRun with --install to apply it.")
        return 0
    try:
        backup = install(info, lambda m: print("  %s" % m))
    except Exception as e:
        print("Failed: %s" % e)
        return 1
    print("Done. Backup: %s" % backup)
    print("Restart Srutilekha from Workspace > Scripts in DaVinci Resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
