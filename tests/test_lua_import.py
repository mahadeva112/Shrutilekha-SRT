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
    start = text.index("local function import_srt_to_new_track(")
    end = text.index("\nend\n", start) + len("\nend\n")
    return text[start:end]


HARNESS = r"""
local logs = {}
function log(s) logs[#logs + 1] = s end
tc = "01:00:00:00"
local CUES = {100, 200, 300}          -- the SRT's cue start frames

local function make_timeline(tracks, opts)
    opts = opts or {}
    local tl = {tracks = tracks}
    local function item(f) return {GetStart = function() return f end, GetName = function() return "cue" end} end
    function tl:GetTrackCount(kind) return #self.tracks end
    function tl:GetItemListInTrack(kind, i)
        local out = {}
        for _, f in ipairs(self.tracks[i].items) do out[#out + 1] = item(f) end
        return out
    end
    function tl:AddTrack(kind) self.tracks[#self.tracks + 1] = {items = {}, locked = false}; return true end
    function tl:DeleteTrack(kind, i) table.remove(self.tracks, i); return true end
    function tl:SetCurrentTimecode(t) return true end
    if not opts.no_locks then
        function tl:GetIsTrackLocked(kind, i) return self.tracks[i].locked end
        function tl:SetTrackLock(kind, i, v) self.tracks[i].locked = v; return true end
    end
    return tl
end

local function make_pool(tl, opts)
    opts = opts or {}
    local mp = {}
    function mp:ImportMedia(files) return {{}} end
    function mp:AppendToTimeline(clips)
        if opts.fail_append then return false end
        for _, t in ipairs(tl.tracks) do
            if not t.locked then
                local after = 0
                for _, f in ipairs(t.items) do after = math.max(after, f + 50) end
                for _, f in ipairs(CUES) do t.items[#t.items + 1] = f + after end
                return true
            end
        end
        return false
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
    print(string.format("RESULT %s ok=%s landed=%s created=%s starts=%s locks=%s tracks=%d err=%s",
        name, tostring(ok), tostring(landed), tostring(created), starts(items),
        table.concat(locks), #tl.tracks, (tostring(err):gsub("%s", "_"))))
end

-- An earlier run's cues on track 1: the new ones must still go to a fresh track, on time.
timeline = make_timeline({{items = {5000, 9000}, locked = false}})
report("occupied", timeline, import_srt_to_new_track(make_pool(timeline), "x.srt"))

-- A track the user locked stays locked; an unlocked one is unlocked again.
timeline = make_timeline({{items = {5000}, locked = true}, {items = {7000}, locked = false}})
report("userlock", timeline, import_srt_to_new_track(make_pool(timeline), "x.srt"))

-- A Resolve without the lock methods still imports (as before the fix).
timeline = make_timeline({{items = {5000}, locked = false}}, {no_locks = true})
report("nolocks", timeline, import_srt_to_new_track(make_pool(timeline), "x.srt"))

-- A failed append puts the locks back and removes the empty track.
timeline = make_timeline({{items = {5000}, locked = false}})
report("failed", timeline, import_srt_to_new_track(make_pool(timeline, {fail_append = true}), "x.srt"))
print("LOGS " .. table.concat(logs, " | "))
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
        cls.results = {}
        for line in cls.output.splitlines():
            if line.startswith("RESULT "):
                name, *pairs = line.split()[1:]
                cls.results[name] = dict(p.split("=", 1) for p in pairs)

    def result(self, name):
        self.assertIn(name, self.results, self.output)
        return self.results[name]

    def test_cues_go_to_a_fresh_track_at_their_own_times(self):
        r = self.result("occupied")
        self.assertEqual((r["ok"], r["landed"], r["created"]), ("true", "2", "true"))
        self.assertEqual(r["starts"], "100,200,300")       # not after the old cues
        self.assertEqual(r["locks"], "--")                 # track 1 unlocked again

    def test_only_tracks_this_run_locked_are_unlocked(self):
        r = self.result("userlock")
        self.assertEqual((r["landed"], r["starts"]), ("3", "100,200,300"))
        self.assertEqual(r["locks"], "L--")

    def test_resolve_without_lock_methods_still_imports(self):
        r = self.result("nolocks")
        self.assertEqual(r["ok"], "true")
        self.assertEqual(r["landed"], "1")                 # the old behaviour, but no error
        self.assertIn("WARNING: the new cues share a track", self.output)

    def test_failed_append_restores_locks_and_drops_the_empty_track(self):
        r = self.result("failed")
        self.assertEqual(r["ok"], "false")
        self.assertEqual((r["locks"], r["tracks"]), ("-", "1"))


if __name__ == "__main__":
    unittest.main()
