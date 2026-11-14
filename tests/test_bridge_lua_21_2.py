"""resolve_bridge.lua under Resolve 21.2's Lua rules, run in Resolve's own Lua.

Resolve 21.2 (checked on 21.2.0.6 Free, 2026-11-14) removed io, loadfile,
dofile and fusion:SavePrefs, and flushes SetPrefs to disk only every ~30 s.
fusion:OpenFile(path, 1|2) with ReadLine/WriteLine still works. The harness
recreates exactly that host, then the real BridgeClient talks to it.
Skipped where DaVinci Resolve (fuscript.exe) is not installed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from resolve_bridge import BridgeClient, RemoteObject, lua_value
from tray_helper import launch_signal

ROOT = Path(__file__).resolve().parents[1]
FUSCRIPT = shutil.which("fuscript") or os.path.join(
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    "Blackmagic Design", "DaVinci Resolve", "fuscript.exe")

HARNESS = r"""
local real_open = io.open
local prefs = {}
local File = {}
File.__index = File
function File:ReadLine()
    local line = self.h:read("*l")
    return line and (line .. "\n") or nil
end
function File:WriteLine(s) self.h:write(s, "\n"); return #s + 1 end
function File:Write() return nil end            -- 21.2 ignores plain strings
function File:Flush() self.h:flush() end
function File:Close() self.h:close() end
local Fusion = {}
function Fusion:OpenFile(path, mode)
    local h = real_open(path, mode == 1 and "rb" or mode == 2 and "wb" or "x")
    return h and setmetatable({h = h}, File) or nil
end
function Fusion:GetPrefs(k) return prefs[k] end
function Fusion:SetPrefs(k, v) prefs[k] = v end
function Fusion:GetResolve() return resolve end
local Named = {}
Named.__index = Named
function Named:GetName() return self.name end
function Named:SetName(v) self.name = v; return true end
function Named:SetProperties() return false end   -- 21.2: subtitle styles are not valid keys
function Named:GetProperties() return {} end       -- 21.2: empty for subtitle cues
function Named:SetProperty(k, v) self.props = self.props or {}; self.props[k] = v; return true end
function Named:GetProperty(k) return (self.props or {})[k] end
local named = setmetatable({name = ""}, Named)  -- an API object, like Resolve's userdata
resolve = {
    GetVersionString = function() return "21.2.0.6" end,
    GetProductName = function() return "DaVinci Resolve" end,
    GetCurrentProject = function() return named end,
}
fusion, fu = Fusion, Fusion
loadfile, dofile, io = nil, nil, nil            -- what 21.2 removed
"""


@unittest.skipUnless(os.path.exists(FUSCRIPT), "DaVinci Resolve is not installed")
class Resolve212BridgeTests(unittest.TestCase):
    def test_file_mailbox_round_trip_without_loadfile_or_saveprefs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "resolve-bridge"
            folder.mkdir()
            source = (ROOT / "resolve_bridge.lua").read_text(encoding="utf-8")
            source = source.replace('"__SRUTILEKHA_MAILBOX__"', lua_value(folder.as_posix()))
            script = folder / "bridge.lua"
            script.write_text(HARNESS + "\n" + source, encoding="utf-8")
            bridge = subprocess.Popen([FUSCRIPT, "-l", "lua", str(script)], stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            try:
                # The prefs file never changes, as on 21.2 before its periodic flush.
                client = BridgeClient(folder, folder / "Fusion.prefs", timeout=15)
                info, resolve = client.connect()
                self.assertEqual(info["version"], "21.2.0.6")
                self.assertEqual(resolve.GetProductName(), "DaVinci Resolve")
                project = resolve.GetCurrentProject()
                self.assertIsInstance(project, RemoteObject)
                long_name = "বাংলা, captions " * 60      # > 1 KB; commas and multibyte text
                self.assertTrue(project.SetName(long_name))
                self.assertEqual(project.GetName(), long_name)
                self.assertTrue(project.SetProperty("fontFace", "Nirmala UI"))   # native fallback
                self.assertEqual(project.GetProperty("fontFace"), "Nirmala UI")
                with patch("tray_helper.user_dir", return_value=folder.parent):
                    self.assertEqual(launch_signal()[0], info["session"])   # instant, not via prefs
                self.assertEqual(list(folder.glob("response-*.txt")), [])
                self.assertTrue(client.request({"op": "stop"}))
                bridge.wait(timeout=10)
            finally:
                if bridge.poll() is None:
                    bridge.kill()
                output = bridge.communicate()[0]
            self.assertNotIn("does not support", output)


if __name__ == "__main__":
    unittest.main()
