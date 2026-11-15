"""import_srt_to_new_track from audio_to_srt.lua, run in Resolve's own Lua.

The fake timeline behaves the way Resolve did on 2026-11-14: an appended
subtitle clip goes to the first unlocked subtitle track, after the cues already
on it. Skipped where DaVinci Resolve (fuscript.exe) is not installed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FUSCRIPT = shutil.which("fuscript") or os.path.join(
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    "Blackmagic Design", "DaVinci Resolve", "fuscript.exe")


def import_function():
    text = (ROOT / "audio_to_srt.lua").read_text(encoding="utf-8").replace("\r\n", "\n")
    # place_srt does the work; import_srt_to_new_track wraps it to put the
    # playhead back, so both are taken, in the order the script has them.
    start = text.index("local function place_srt(")
    wrapper = text.index("local function import_srt_to_new_track(", start)
    end = text.index("\nend\n", wrapper) + len("\nend\n")
    return text[start:end]


HARNESS = r"""
local logs = {}
function log(s) logs[#logs + 1] = s end
tc = "01:00:00:00"
tlStart = 0
local CUES = {100, 200, 300}          -- the SRT's cue start frames

local function make_timeline(tracks, opts)
    opts = opts or {}
    local tl = {tracks = tracks, playhead = "01:00:10:00"}   -- where the user left it
    local function item(f) return {GetStart = function() return f end, GetName = function() return "cue" end} end
    function tl:GetTrackCount(kind) return #self.tracks end
    function tl:GetItemListInTrack(kind, i)
        local out = {}
        for _, f in ipairs(self.tracks[i].items) do out[#out + 1] = item(f) end
        return out
    end
    function tl:AddTrack(kind) self.tracks[#self.tracks + 1] = {items = {}, locked = false}; return true end
    function tl:DeleteTrack(kind, i) table.remove(self.tracks, i); return true end
    function tl:GetCurrentTimecode() return self.playhead end
    function tl:SetCurrentTimecode(t) self.playhead = t; return true end
    if opts.old_lock_names then
        -- Resolve 21.0 and earlier: GetTrackLock, no GetIsTrackLocked.
        function tl:GetTrackLock(kind, i) return self.tracks[i].locked end
        function tl:SetTrackLock(kind, i, v) self.tracks[i].locked = v; return true end
    elseif not opts.no_locks then
        function tl:GetIsTrackLocked(kind, i) return self.tracks[i].locked end
        function tl:SetTrackLock(kind, i, v) self.tracks[i].locked = v; return true end
    end
    if opts.delete then
        function tl:DeleteClips(items, ripple)
            local gone = {}
            for _, it in ipairs(items) do gone[it:GetStart()] = true end
            for _, t in ipairs(self.tracks) do
                local keep = {}
                for _, f in ipairs(t.items) do if not gone[f] then keep[#keep + 1] = f end end
                t.items = keep
            end
            return true
        end
    end
    return tl
end

-- opts.clipinfo: honours {mediaPoolItem, trackIndex, recordFrame}; otherwise a
-- clipInfo append places nothing. opts.refuse_locked: a plain append places
-- nothing while any subtitle track is locked (Resolve on 2026-11-14).
-- opts.fail: nothing is ever placed. Plain appends go to the first unlocked
-- track, after the cues already on it. Every call returns nil, so only the
-- timeline itself tells whether an append worked.
local function make_pool(tl, opts)
    opts = opts or {}
    local mp = {}
    function mp:ImportMedia(files) return {{}} end
    function mp:AppendToTimeline(clips)
        tl.playhead = "01:59:00:00"       -- Resolve leaves it past the appended clip
        if opts.fail then return nil end
        local info = clips[1]
        if info.mediaPoolItem then
            if opts.video_end then
                -- An older Resolve: the whole run lands at the end of the video.
                local t = tl.tracks[info.trackIndex]
                for _, f in ipairs(CUES) do t.items[#t.items + 1] = f + opts.video_end end
                return nil
            end
            if not opts.clipinfo then return nil end
            local t = tl.tracks[info.trackIndex]
            for _, f in ipairs(CUES) do t.items[#t.items + 1] = f + info.recordFrame end
            return nil
        end
        for _, t in ipairs(tl.tracks) do
            if t.locked and opts.refuse_locked then return nil end
        end
        for _, t in ipairs(tl.tracks) do
            if not t.locked then
                local after = 0
                for _, f in ipairs(t.items) do after = math.max(after, f + 50) end
                for _, f in ipairs(CUES) do t.items[#t.items + 1] = f + after end
                return nil
            end
        end
        return nil
    end
    return mp
end

local function starts(items)
    local s = {}
    for _, it in ipairs(items or {}) do s[#s + 1] = it:GetStart() end
    return table.concat(s, ",")
end

local function report(name, tl, ok, landed, items, created, err)
    local locks = {}
    for i, t in ipairs(tl.tracks) do locks[#locks + 1] = t.locked and "L" or "-" end
    print(string.format("RESULT %s ok=%s landed=%s created=%s starts=%s locks=%s tracks=%d playhead=%s err=%s",
        name, tostring(ok), tostring(landed), tostring(created), starts(items),
        table.concat(locks), #tl.tracks, tostring(tl.playhead), (tostring(err):gsub("%s", "_"))))
    print("LOGS " .. name .. " " .. table.concat(logs, " | "))
    logs = {}
end

local function run(name, tracks, topts, popts, firstFrame)
    timeline = make_timeline(tracks, topts)
    report(name, timeline, import_srt_to_new_track(make_pool(timeline, popts), "x.srt", firstFrame))
end

run("clipinfo", {{items = {5000, 9000}, locked = false}}, {}, {clipinfo = true})
run("locks", {{items = {5000, 9000}, locked = false}}, {}, {})
run("refused", {{items = {5000, 9000}, locked = false}}, {}, {refuse_locked = true})
run("userlock", {{items = {5000}, locked = true}, {items = {7000}, locked = false}}, {}, {})
run("nolocks", {{items = {5000}, locked = false}}, {no_locks = true}, {})
run("failed", {{items = {5000}, locked = false}}, {}, {fail = true})
run("videoend", {{items = {5000, 9000}, locked = false}}, {old_lock_names = true, delete = true},
    {video_end = 20000}, 100)
run("videoend_nodelete", {{items = {5000, 9000}, locked = false}}, {old_lock_names = true},
    {video_end = 20000}, 100)
"""


@unittest.skipUnless(os.path.exists(FUSCRIPT), "DaVinci Resolve's fuscript is not installed")
class LuaImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "harness.lua"
            script.write_text(import_function() + HARNESS, encoding="utf-8")
            out = subprocess.run([FUSCRIPT, "-l", "lua", str(script)], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=60)
        cls.output = out.stdout + out.stderr
        cls.results, cls.logs = {}, {}
        for line in cls.output.splitlines():
            if line.startswith("RESULT "):
                name, *pairs = line.split()[1:]
                cls.results[name] = dict(p.split("=", 1) for p in pairs)
            elif line.startswith("LOGS "):
                name, _, text = line[5:].partition(" ")
                cls.logs[name] = text

    def result(self, name):
        self.assertIn(name, self.results, self.output)
        return self.results[name]

    def test_clipinfo_places_cues_on_the_new_track_at_their_own_times(self):
        r = self.result("clipinfo")
        self.assertEqual((r["ok"], r["landed"], r["created"]), ("true", "2", "true"))
        self.assertEqual(r["starts"], "100,200,300")       # once, and not after the old cues
        self.assertEqual(r["locks"], "--")
        self.assertNotIn("locked", self.logs["clipinfo"])  # no later attempt ran

    def test_locking_steers_a_plain_append_to_the_new_track(self):
        r = self.result("locks")
        self.assertEqual((r["landed"], r["created"], r["starts"]), ("2", "true", "100,200,300"))
        self.assertEqual(r["locks"], "--")                 # track 1 unlocked again

    def test_a_refused_locked_append_falls_back_instead_of_stopping(self):
        # What happened on 2026-11-14: the run must still import, as before.
        r = self.result("refused")
        self.assertEqual((r["ok"], r["landed"]), ("true", "1"))
        self.assertEqual(r["locks"], "-")
        self.assertIn("Resolve placed nothing with 1 other subtitle track(s) locked", self.logs["refused"])
        self.assertIn("Placed the captions with a plain append", self.logs["refused"])
        self.assertIn("WARNING: the new cues share a track", self.logs["refused"])

    def test_only_tracks_this_run_locked_are_unlocked(self):
        r = self.result("userlock")
        self.assertEqual((r["landed"], r["starts"]), ("3", "100,200,300"))
        self.assertEqual(r["locks"], "L--")

    def test_resolve_without_lock_methods_still_imports(self):
        r = self.result("nolocks")
        self.assertEqual((r["ok"], r["landed"]), ("true", "1"))

    def test_whole_script_and_packaged_script_compile(self):
        from scripts.package_lua import package
        with tempfile.TemporaryDirectory() as tmp:
            packaged = Path(tmp) / "Srutilekha.lua"
            package(ROOT / "audio_to_srt.lua", packaged)
            check = Path(tmp) / "compile.lua"
            check.write_text("".join(
                'local f, e = loadfile(%r) print(f and "COMPILED" or ("BROKEN " .. tostring(e)))\n'
                % str(p).replace("\\", "/") for p in (ROOT / "audio_to_srt.lua", packaged)), encoding="utf-8")
            out = subprocess.run([FUSCRIPT, "-l", "lua", str(check)], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual((out.stdout + out.stderr).count("COMPILED"), 2, out.stdout + out.stderr)

    def test_cues_put_at_the_video_end_are_taken_back_and_placed_again(self):
        # An older Resolve: the clipInfo append put the run at the end of the
        # video and there is no MoveItems to bring it back.
        r = self.result("videoend")
        self.assertEqual((r["ok"], r["landed"], r["created"]), ("true", "2", "true"))
        self.assertEqual(r["starts"], "100,200,300")
        self.assertEqual(r["locks"], "--")
        self.assertIn("Took the 3 new cue(s) off track 2 again", self.logs["videoend"])
        self.assertIn("Placed the captions with 1 other subtitle track(s) locked", self.logs["videoend"])

    def test_misplaced_cues_stay_when_they_cannot_be_taken_back(self):
        r = self.result("videoend_nodelete")
        self.assertEqual((r["ok"], r["landed"], r["starts"]), ("true", "2", "20100,20200,20300"))
        self.assertIn("Keeping the cues where Resolve put them", self.logs["videoend_nodelete"])

    def test_playhead_goes_back_where_the_user_left_it(self):
        for name in ("clipinfo", "locks", "failed", "videoend"):
            with self.subTest(name=name):
                self.assertEqual(self.result(name)["playhead"], "01:00:10:00")

    def test_nothing_placed_reports_failure_and_drops_the_empty_track(self):
        r = self.result("failed")
        self.assertEqual(r["ok"], "false")
        self.assertEqual((r["locks"], r["tracks"]), ("-", "1"))


if __name__ == "__main__":
    unittest.main()
