-- audio_to_srt.lua  —  Srutilekha  (Workspace -> Scripts -> Srutilekha)
-- Transcribes the first audio track via ElevenLabs and imports subtitles.
-- Cross-platform: Mac + Windows. All dialogs use dialog.py (tkinter).

-- Do NOT use package.config here. Resolve 21.1's Lua script host stopped
-- exposing the `package` table, so `package.config:sub(1,1)` errors with
-- "attempt to index global 'package' (a nil value)" on line 1 of the script —
-- the menu entry then does nothing at all, with the error only visible in
-- Support\logs\ResolveDebug.txt. SystemRoot/USERPROFILE are set on every
-- Windows session and on no macOS one, and os.getenv is always available.
local IS_WINDOWS = (os.getenv("SystemRoot") or os.getenv("USERPROFILE")) ~= nil
local SEP = IS_WINDOWS and "\\" or "/"

local function get_project_dir()
    local config = IS_WINDOWS
        and (os.getenv("USERPROFILE") .. "\\.audio_to_srt_path")
        or  (os.getenv("HOME")        .. "/.audio_to_srt_path")
    local f = io.open(config)
    if f then
        local p = f:read("*l"); f:close()
        if p and p:match("%S") then return p:match("^%s*(.-)%s*$") end
    end
    return IS_WINDOWS
        and (os.getenv("USERPROFILE") .. "\\DaVinci-Audio2SRT")
        or  (os.getenv("HOME") .. "/DaVinci-Audio2SRT")
end

local PROJECT_DIR = get_project_dir()

local TRANSCRIBE_PY = PROJECT_DIR .. SEP .. "transcribe.py"
local DIALOG_PY     = PROJECT_DIR .. SEP .. "dialog.py"
local LOADER_PY     = PROJECT_DIR .. SEP .. "loader.pyw"
local LOGS_DIR      = PROJECT_DIR .. SEP .. "logs"
local LOG_FILE      = LOGS_DIR .. SEP .. "audio_to_srt.log"

local function find_python()
    -- IMPORTANT: bare "python" on PATH must remain the LAST Windows fallback
    -- and ideally never be hit. On modern Windows, %LOCALAPPDATA%\Microsoft\
    -- WindowsApps\python.exe is an App Execution Alias stub that satisfies
    -- file-existence checks but prints "Python was not found..." when run.
    -- We list real install locations (including the official `py` launcher)
    -- ahead of it so io.open() picks a working interpreter first.
    local candidates = IS_WINDOWS and {
        os.getenv("LOCALAPPDATA") .. "\\Python\\bin\\python.exe",  -- some 3rd-party installers
        os.getenv("LOCALAPPDATA") .. "\\Programs\\Python\\Python314\\python.exe",
        os.getenv("LOCALAPPDATA") .. "\\Programs\\Python\\Python313\\python.exe",
        os.getenv("LOCALAPPDATA") .. "\\Programs\\Python\\Python312\\python.exe",
        os.getenv("LOCALAPPDATA") .. "\\Programs\\Python\\Python311\\python.exe",
        "C:\\Python314\\python.exe",
        "C:\\Python313\\python.exe",
        "C:\\Python312\\python.exe",
        "C:\\Python311\\python.exe",
        (os.getenv("SystemRoot") or "C:\\Windows") .. "\\py.exe",  -- official py launcher
        "python",
    } or {
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        "python3",
    }
    for _, p in ipairs(candidates) do
        local f = io.open(p)
        if f then f:close(); return p end
    end
    return candidates[#candidates]
end

local PYTHON3 = find_python()

-- pythonw.exe (windowless) sibling of python.exe — used to launch the
-- loader so no blank CMD window appears in Resolve.
local function find_pythonw()
    if not IS_WINDOWS then return PYTHON3 end
    -- python.exe -> pythonw.exe, py.exe -> pyw.exe
    local cand = PYTHON3:gsub("python%.exe$", "pythonw.exe"):gsub("\\py%.exe$", "\\pyw.exe")
    local f = io.open(cand)
    if f then f:close(); return cand end
    return PYTHON3
end
local PYTHONW = find_pythonw()

-- os.execute() on Windows goes through a *visible* cmd.exe — Resolve's script
-- host gives it a console window. Calling mkdir on every log line therefore
-- made a black window blink several times on each launch. Opening the log for
-- append is itself the existence check: it only fails when the directory is
-- missing, so the shell-out happens at most once per session (and normally
-- never, since the folder survives between runs).
local logs_dir_ready = false
local function open_log()
    local f = io.open(LOG_FILE, "a")
    if f then logs_dir_ready = true; return f end
    if not logs_dir_ready then
        if IS_WINDOWS then
            os.execute('if not exist "' .. PROJECT_DIR .. '\\logs" mkdir "' .. PROJECT_DIR .. '\\logs"')
        else
            os.execute('mkdir -p "' .. PROJECT_DIR .. '/logs"')
        end
        logs_dir_ready = true
    end
    return io.open(LOG_FILE, "a")
end

local function ensure_logs_dir()
    local f = open_log()
    if f then f:close() end
end

local function log(msg)
    local f = open_log()
    if f then f:write(os.date("%Y-%m-%d %H:%M:%S") .. "  " .. msg .. "\n"); f:close() end
    print(msg)
end

local function pydialog(...)
    local args = {...}
    -- PYTHONW, not PYTHON3, and quoted. Two separate problems here before:
    --   * the interpreter was interpolated with %s, so an install path
    --     containing a space ("C:\Program Files\...\python.exe") split into two
    --     tokens and the dialog never opened;
    --   * python.exe is a console binary, and Resolve is a GUI process with no
    --     console, so Windows allocated one for every alert -- the black box
    --     that blinks whenever this script reports anything. The loader launch
    --     goes to great lengths to avoid exactly that; dialogs were still doing
    --     it. pythonw.exe is GUI-subsystem and opens no console.
    local cmd = string.format('%q %q', PYTHONW, DIALOG_PY)
    for _, a in ipairs(args) do
        -- strip newlines: literal \n in cmd.exe splits the command mid-argument
        local clean = tostring(a):gsub("[\r\n]+", " ")
        cmd = cmd .. " " .. string.format("%q", clean)
    end
    cmd = cmd .. (IS_WINDOWS and " 2>nul" or " 2>/dev/null")
    local handle = io.popen(cmd)
    if not handle then return "" end
    local result = handle:read("*a") or ""; handle:close()
    return result:match("^%s*(.-)%s*$")
end

local function alert(title, msg)
    pydialog("alert", title, msg)
end

local function alert_error(title, msg)
    pydialog("alert_error", title, msg)
end

local r = resolve or (fusion and fusion:GetResolve())
if not r then
    alert_error("Srutilekha", "Cannot connect to DaVinci Resolve.")
    return
end

log("Script started")
local pm      = r:GetProjectManager()
local project = pm:GetCurrentProject()
if not project then
    alert_error("Srutilekha", "No project is open.")
    return
end

local timeline = project:GetCurrentTimeline()
if not timeline then
    alert_error("Srutilekha", "No active timeline. Open a timeline in the Edit page first.")
    return
end

local trackCount = timeline:GetTrackCount("audio")
if trackCount == 0 then
    alert_error("Srutilekha", "No audio tracks in the current timeline.")
    return
end

local trackItems = {}
for i = 1, trackCount do
    local name = timeline:GetTrackName("audio", i) or ("Audio " .. i)
    trackItems[#trackItems + 1] = "Track " .. i .. ": " .. name
end

-- ── Single-window UI: launch loader.pyw, it shows the form first, then
--    transitions in place to the progress view once the user submits.
--    We pass it the track list via prompt.json; it writes selection.json
--    back as soon as the user clicks Generate Subtitles.
local LOGS_DIR    = PROJECT_DIR .. SEP .. "logs"
-- Same folder log() writes into, so this is already satisfied by the first
-- log call above — no second shell-out (and no second console flash).
ensure_logs_dir()

-- Every launch gets its own handshake files. They used to have fixed names,
-- which broke as soon as two instances overlapped (script started, loader left
-- open, script started again): both instances read the same selection.json on
-- Submit and transcribed in parallel, each into its own os.tmpname() SRT, so
-- one of them then failed with "Transcription produced no output".
-- The id is time + this table's address — unique even within the same second.
local RUN_ID = string.format("%d-%s", os.time(),
    tostring({}):match("[%x]+$") or tostring(os.clock()):gsub("%D", ""))
local RUN_SUFFIX = "-" .. RUN_ID

local markerPath    = LOGS_DIR .. SEP .. "current_run.txt"
local promptPath    = LOGS_DIR .. SEP .. "prompt" .. RUN_SUFFIX .. ".json"
local selectionPath = LOGS_DIR .. SEP .. "selection" .. RUN_SUFFIX .. ".json"
local loaderLog     = LOG_FILE .. ".transcribe"
local donePath      = LOGS_DIR .. SEP .. "transcribe" .. RUN_SUFFIX .. ".done"
local argsPath      = LOGS_DIR .. SEP .. "transcribe_args" .. RUN_SUFFIX .. ".txt"
local resultPath    = LOGS_DIR .. SEP .. "transcribe" .. RUN_SUFFIX .. ".result"
local ackPath       = LOGS_DIR .. SEP .. "transcribe" .. RUN_SUFFIX .. ".ack"
-- Scratch files for the ShellExecute launch route (see the launch section).
local vbsPath       = LOGS_DIR .. SEP .. "launch" .. RUN_SUFFIX .. ".vbs"
local vbsOkPath     = LOGS_DIR .. SEP .. "launch" .. RUN_SUFFIX .. ".ok"
-- Records the track created by the last generation so "Undo" can remove it.
local lastGenPath   = LOGS_DIR .. SEP .. "last_gen.txt"
-- Clip ranges for the timeline remap. Per-run like every other handshake file:
-- with a fixed name, two overlapping launches wrote the same file and each
-- transcription remapped its words onto the other's clip layout. Declared here
-- so cleanup_run() below can see it.
local rangesPath    = LOGS_DIR .. SEP .. "clip_ranges" .. RUN_SUFFIX .. ".txt"

-- Retire the previous run: drop its already-consumed input files and claim the
-- marker. A still-running transcription keeps its .done/.result/.ack, so it
-- finishes and reports normally; only a loader still sitting on the form
-- reacts to the marker change (it watches this file and closes itself).
local function read_file(p)
    local f = io.open(p, "r")
    if not f then return nil end
    local s = f:read("*a") or ""; f:close()
    return s:match("^%s*(.-)%s*$")
end

local prevRun = read_file(markerPath)
if prevRun and prevRun ~= "" and prevRun ~= RUN_ID then
    local prevSuffix = "-" .. prevRun
    os.remove(LOGS_DIR .. SEP .. "prompt" .. prevSuffix .. ".json")
    os.remove(LOGS_DIR .. SEP .. "selection" .. prevSuffix .. ".json")
    os.remove(LOGS_DIR .. SEP .. "selection" .. prevSuffix .. ".json.tmp")
    os.remove(LOGS_DIR .. SEP .. "transcribe_args" .. prevSuffix .. ".txt")
    os.remove(LOGS_DIR .. SEP .. "clip_ranges" .. prevSuffix .. ".txt")
    os.remove(LOGS_DIR .. SEP .. "launch" .. prevSuffix .. ".vbs")
    os.remove(LOGS_DIR .. SEP .. "launch" .. prevSuffix .. ".ok")
    log("Superseding earlier run " .. prevRun)
end
-- Legacy fixed-name leftovers from before per-run naming.
os.remove(LOGS_DIR .. SEP .. "selection.json")
os.remove(LOGS_DIR .. SEP .. "transcribe.done")
os.remove(LOGS_DIR .. SEP .. "transcribe_args.txt")
os.remove(LOGS_DIR .. SEP .. "transcribe.result")
os.remove(LOGS_DIR .. SEP .. "transcribe.ack")

local mf = io.open(markerPath, "wb")
if mf then mf:write(RUN_ID); mf:close() end

-- True once a newer launch has claimed the marker — this instance must bow out.
local function superseded()
    local cur = read_file(markerPath)
    return cur ~= nil and cur ~= "" and cur ~= RUN_ID
end

-- Every scratch file this run owns. rangesPath and the handshake sentinels used
-- to be left behind on the cancel path, which is why logs/ accumulated stray
-- transcribe-<id>.ack files: only the *next* run's supersede sweep cleared some
-- of them, and nothing ever cleared .ack at all.
local function cleanup_run()
    os.remove(promptPath); os.remove(selectionPath); os.remove(argsPath)
    os.remove(vbsPath); os.remove(vbsOkPath)
    os.remove(donePath); os.remove(resultPath); os.remove(ackPath)
    if rangesPath then os.remove(rangesPath) end
end

-- ── Bounded waits ───────────────────────────────────────────────────────────
-- Both handshake waits used to be `while true do ... end` with no timeout and no
-- supersede check. If the loader died -- killed, crashed, or closed by Windows --
-- this script waited forever inside Resolve, and with the old spin-loop sleep it
-- did so at 100% CPU. Every wait now has a ceiling and notices a newer run.

-- Forward declaration. The sleep implementation is defined further down (it
-- probes the FFI and bmd.wait first), but both waits below call it. Declaring
-- the local *here* is what makes those calls resolve to it: a reference written
-- above the `local` compiles to a global lookup instead, which is nil, so the
-- first poll iteration -- the first time the sentinel is not there yet -- died
-- with "attempt to call a nil value" and took the whole script with it.
local sleep_ms

-- Wait for the loader's completion sentinel. Returns its exit code, or nil if it
-- never arrived (timeout / superseded).
local function wait_for_done(timeout_s)
    local deadline = os.time() + (timeout_s or 7200)
    while true do
        local df = io.open(donePath, "r")
        if df then
            local s = df:read("*a") or ""
            df:close()
            return tonumber(s:match("(-?%d+)")) or 1
        end
        if superseded() then return nil, "superseded" end
        if os.time() > deadline then return nil, "timeout" end
        sleep_ms(250)
    end
end

-- Wait for the loader to acknowledge the result screen, so the window is not
-- torn down before the user has read it. Best-effort: the run is already done.
local function wait_for_ack(timeout_s)
    local deadline = os.time() + (timeout_s or 300)
    while true do
        local ak = io.open(ackPath, "r")
        if ak then ak:close(); os.remove(ackPath); return true end
        if os.time() > deadline then return false end
        sleep_ms(250)
    end
end

-- Minimal JSON escape for our case (track names, default settings).
local function json_escape(s)
    return (tostring(s)
        :gsub("\\", "\\\\")
        :gsub('"', '\\"')
        :gsub("\n", "\\n")
        :gsub("\r", "\\r")
        :gsub("\t", "\\t"))
end

local jsonParts = {'{"items":['}
for i, it in ipairs(trackItems) do
    jsonParts[#jsonParts + 1] = (i > 1 and ',' or '') .. '"' .. json_escape(it) .. '"'
end
jsonParts[#jsonParts + 1] = '],'

-- Timeline context for the form's title bar and the preview's spec plate. The
-- UI only renders what is actually present here, so a Resolve build that
-- doesn't answer these settings simply shows less rather than showing a guess.
local tlName = timeline.GetName and timeline:GetName() or nil
local resW   = timeline.GetSetting and timeline:GetSetting("timelineResolutionWidth") or nil
local resH   = timeline.GetSetting and timeline:GetSetting("timelineResolutionHeight") or nil
local tlFps  = timeline.GetSetting and timeline:GetSetting("timelineFrameRate") or nil
if tlName and tlName ~= "" then
    jsonParts[#jsonParts + 1] = '"timeline":"' .. json_escape(tlName) .. '",'
end
if resW and resH and tostring(resW) ~= "" and tostring(resH) ~= "" then
    jsonParts[#jsonParts + 1] = '"resolution":"' .. json_escape(
        tostring(resW) .. " x " .. tostring(resH)) .. '",'
end
if tlFps and tostring(tlFps) ~= "" then
    -- Resolve hands frame rate back as "25.0" as often as "25"; trim the
    -- pointless decimal so the plate reads "25 fps", not "25.0 fps".
    local fps = tostring(tlFps):gsub("%.0+$", "")
    jsonParts[#jsonParts + 1] = '"fps":"' .. json_escape(fps) .. '",'
end

jsonParts[#jsonParts + 1] = '"defaults":{"settings":"15,1,2","punct":0,"lang":"Auto-detect","diarize":0,"min_secs":"0.4","cps":"25","text_size":"55","outline":1,"shadow":1,"font":"Auto (by language)","font_style":"Auto","color":""}}'
local pf = io.open(promptPath, "wb")
if not pf then
    alert_error("Srutilekha", "Cannot write prompt file: " .. promptPath)
    return
end
pf:write(table.concat(jsonParts))
pf:close()

local loaderExists = io.open(LOADER_PY)
if not loaderExists then
    alert_error("Srutilekha", "loader.pyw not found: " .. LOADER_PY)
    return
end
loaderExists:close()

local loaderArgs = string.format(
    '%q %q --prompt %q --selection %q --args-file %q --done %q --log %q --python %q --script %q --result %q --ack %q --run-id %q --run-marker %q',
    PYTHONW, LOADER_PY, promptPath, selectionPath, argsPath, donePath, loaderLog, PYTHON3, TRANSCRIBE_PY, resultPath, ackPath, RUN_ID, markerPath)

local launchCmd
if IS_WINDOWS then
    launchCmd = 'start "" ' .. loaderArgs
else
    launchCmd = loaderArgs .. ' &'
end

-- The same command line for the shell-free path below. It cannot reuse
-- loaderArgs: Lua's %q escapes for *Lua*, so every path separator comes out
-- doubled. cmd.exe and the CRT's argv parser both shrug that off (Win32
-- collapses repeated separators), but CreateProcess takes the program token
-- literally, so there is no reason to hand it something that needs forgiving.
-- Plain one-level quoting; none of these paths contain a quote or end in a
-- separator, which are the only cases this would not cover.
local function winquote(s)
    return '"' .. tostring(s):gsub('"', '\\"') .. '"'
end
local hiddenCmd = table.concat({
    winquote(PYTHONW),      winquote(LOADER_PY),
    "--prompt",      winquote(promptPath),
    "--selection",   winquote(selectionPath),
    "--args-file",   winquote(argsPath),
    "--done",        winquote(donePath),
    "--log",         winquote(loaderLog),
    "--python",      winquote(PYTHON3),
    "--script",      winquote(TRANSCRIBE_PY),
    "--result",      winquote(resultPath),
    "--ack",         winquote(ackPath),
    "--run-id",      winquote(RUN_ID),
    "--run-marker",  winquote(markerPath),
}, " ")

-- Launch with no console flash where possible.
--
-- os.execute() always routes through cmd.exe on Windows, and since Resolve is
-- a GUI process with no console of its own, Windows allocates a brand new one
-- for that cmd — the black box that blinks on screen at every launch. There is
-- no way to pass CREATE_NO_WINDOW through os.execute.
--
-- Fusion's Lua is LuaJIT, so when the FFI is reachable we skip the shell
-- entirely and call WinExec with SW_HIDE: pythonw.exe is a GUI-subsystem
-- binary, so no console is ever created. WinExec is used rather than
-- CreateProcessW because its signature is two scalars — no structs to lay out
-- by hand, nothing that can corrupt memory if the host's FFI differs.
-- Everything is wrapped in pcall; any failure falls through to the old path,
-- so the worst case is exactly today's behaviour.
local function winexec_hidden(cmdline)
    local ok, ffi = pcall(require, "ffi")
    if not ok or type(ffi) ~= "table" then return false end
    -- cdef throws if the symbol is already declared in this LuaJIT state,
    -- which is harmless — the declaration we need is present either way.
    pcall(ffi.cdef, "unsigned int WinExec(const char *lpCmdLine, unsigned int uCmdShow);")
    local called, ret = pcall(function() return ffi.C.WinExec(cmdline, 0) end)
    if not called then return false end
    ret = tonumber(ret)
    -- WinExec reports success as a value greater than 31; anything at or below
    -- that is one of the legacy error codes.
    return ret ~= nil and ret > 31
end

-- Wait without burning a core.
--
-- This used to be `while os.clock() < t do end`, a spin loop, and every wait in
-- this script goes through it -- including the one that sits out the whole
-- transcription. So Resolve held a CPU core at 100% for the entire run. Worse,
-- os.clock() is *process CPU time*, summed across all of Resolve's threads, so
-- the interval it produced varied with how busy Resolve was: under load
-- "250 ms" could elapse in a fraction of that.
--
-- Kernel32's Sleep is the right primitive and LuaJIT's FFI is reachable in
-- Fusion (the launch path above already relies on it). bmd.wait is the
-- documented BMD equivalent for hosts without the FFI. The spin is kept only as
-- a last resort, and even then it is driven by os.time() so it cannot undershoot
-- by a factor of the thread count.
local _sleep_impl = nil
local function _init_sleep()
    if IS_WINDOWS then
        local ok, ffi = pcall(require, "ffi")
        if ok and type(ffi) == "table" then
            pcall(ffi.cdef, "void Sleep(unsigned long dwMilliseconds);")
            local works = pcall(function() ffi.C.Sleep(0) end)
            if works then
                return function(ms) ffi.C.Sleep(ms) end
            end
        end
    end
    if type(bmd) == "table" and type(bmd.wait) == "function" then
        local works = pcall(bmd.wait, 0)
        if works then
            return function(ms) pcall(bmd.wait, ms / 1000.0) end
        end
    end
    if not IS_WINDOWS then
        return function(ms)
            os.execute(string.format("sleep %.3f", ms / 1000.0))
        end
    end
    return function(ms)
        -- Coarse but honest: os.time() is wall-clock seconds.
        local target = os.time() + math.max(1, math.ceil(ms / 1000.0))
        while os.time() < target do end
    end
end

-- Assignment, not `local function`: the local is declared up beside the waits
-- that call it, so a second `local` here would shadow it and leave those calls
-- pointing at nil.
sleep_ms = function(ms)
    if _sleep_impl == nil then _sleep_impl = _init_sleep() end
    _sleep_impl(ms)
end

-- Second console-free door, for hosts where the FFI is not reachable (plain
-- Lua 5.1 rather than LuaJIT, or an FFI the sandbox withholds). ShellExecute
-- never allocates a console either, and Fusion exposes it as
-- bmd.openfileexternal — but it takes no arguments, so it is aimed at a
-- throwaway VBScript that starts the loader itself. .vbs runs under
-- WScript.exe, which is GUI-subsystem, so that stage adds no console of its
-- own, and Run's window style of 0 hides anything the child might open.
--
-- ShellExecute reports nothing back, and a script host blocked by policy or AV
-- would fail silently — leaving no window at all, which is far worse than a
-- flash. So the VBScript stamps an .ok file as its very first act: that file,
-- not the ShellExecute call, is the proof this route worked. It lands within
-- milliseconds of WScript starting, well before Python has even imported Tk,
-- so waiting on it cannot double-launch a loader that was merely slow to boot.
local function vbs_literal(s)
    return '"' .. tostring(s):gsub('"', '""') .. '"'
end

local function shellexec_hidden(cmdline)
    if type(bmd) ~= "table" or type(bmd.openfileexternal) ~= "function" then
        return false
    end
    local vf = io.open(vbsPath, "wb")
    if not vf then return false end
    vf:write(table.concat({
        -- The launch is gated on the .ok stamp actually landing, not merely on
        -- having tried: if the file system object is unavailable the stamp
        -- never appears, Lua falls back to cmd.exe, and this script must not
        -- have started a second loader behind its back.
        'On Error Resume Next',
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        'fso.CreateTextFile(' .. vbs_literal(vbsOkPath) .. ', True).Close',
        'If fso.FileExists(' .. vbs_literal(vbsOkPath) .. ') Then',
        '  CreateObject("WScript.Shell").Run ' .. vbs_literal(cmdline) .. ', 0, False',
        'End If',
        'fso.DeleteFile WScript.ScriptFullName',
        '',
    }, "\r\n"))
    vf:close()
    if not pcall(bmd.openfileexternal, "Open", vbsPath) then
        os.remove(vbsPath)
        return false
    end
    local waited = 0
    while waited < 4000 do
        local okf = io.open(vbsOkPath, "r")
        if okf then
            okf:close()
            os.remove(vbsOkPath)
            return true
        end
        sleep_ms(100)
        waited = waited + 100
    end
    os.remove(vbsPath)
    return false
end

-- Each attempt names itself in the log, so one launch is enough to tell which
-- door this Resolve build actually opened.
local launched = false
if IS_WINDOWS then
    local ok, hidden = pcall(winexec_hidden, hiddenCmd)
    launched = ok and hidden
    if launched then log("Launching loader (hidden via WinExec): " .. hiddenCmd) end
    if not launched then
        local ok2, hidden2 = pcall(shellexec_hidden, hiddenCmd)
        launched = ok2 and hidden2
        if launched then
            log("Launching loader (hidden via ShellExecute + WScript): " .. hiddenCmd)
        else
            log("No console-free launch route available (ffi and bmd both unusable)")
        end
    end
end
if not launched then
    log("Launching loader via cmd.exe — this one flashes a console: " .. launchCmd)
    os.execute(launchCmd)
end

-- Wait for either selection (user submitted) or done (user cancelled).
local chosen, srt_input_path, settings, include_punct, lang_code
local diarize, min_secs, cps
local text_size, outline, shadow, action, srt_posy
local srt_fonts
local cap_font, cap_color, font_style
local words_per, ref_script
while true do
    -- A newer launch has taken over: stop waiting, or this instance would also
    -- act on that launch's submission and race it.
    if superseded() then
        log("Superseded by a newer Srutilekha run — this instance is exiting.")
        os.remove(donePath)
        cleanup_run()
        return
    end
    local df = io.open(donePath, "r")
    if df then
        local s = df:read("*a") or ""; df:close()
        log("User cancelled (loader closed before submit)")
        os.remove(donePath)
        cleanup_run()
        return
    end
    local sf = io.open(selectionPath, "r")
    if sf then
        local body = sf:read("*a") or ""; sf:close()
        chosen        = body:match('"chosen"%s*:%s*"(.-)"')
        srt_input_path = body:match('"srt_input_path"%s*:%s*"(.-)"')
        settings      = body:match('"settings"%s*:%s*"(.-)"')
        include_punct = body:match('"punct"%s*:%s*(%d+)')
        lang_code     = body:match('"lang_code"%s*:%s*"(.-)"')
        diarize       = body:match('"diarize"%s*:%s*(%d+)')
        min_secs      = body:match('"min_secs"%s*:%s*"(.-)"')
        cps           = body:match('"cps"%s*:%s*"(.-)"')
        text_size     = body:match('"text_size"%s*:%s*"(.-)"')
        outline       = body:match('"outline"%s*:%s*(%d+)')
        shadow        = body:match('"shadow"%s*:%s*(%d+)')
        action        = body:match('"action"%s*:%s*"(.-)"')
        cap_font      = body:match('"font"%s*:%s*"(.-)"')
        cap_color     = body:match('"color"%s*:%s*"(.-)"')
        font_style    = body:match('"font_style"%s*:%s*"(.-)"')
        words_per     = body:match('"words_per"%s*:%s*"(.-)"')
        srt_posy      = body:match('"srt_posy"%s*:%s*"(.-)"')
        -- "deva=Vesper Libre|taml=Nirmala UI|...": one installed font per
        -- script, resolved by the loader because only that side can ask the
        -- system what is actually present. See resolve_subtitle_fonts().
        srt_fonts     = body:match('"srt_fonts"%s*:%s*"(.-)"')
        -- The user's own script, to spell names and terms their way. A
        -- Windows path arrives with its backslashes JSON-escaped (\\), so
        -- undo that or the file is never found.
        ref_script    = body:match('"ref_script"%s*:%s*"(.-)"')
        if ref_script then ref_script = ref_script:gsub("\\\\", "\\") end
        if chosen and settings then break end
    end
    sleep_ms(150)
end
-- Both are fully consumed now; the loader has them in memory.
os.remove(promptPath); os.remove(selectionPath)
if not include_punct or include_punct == "" then include_punct = "0" end
-- "auto" makes transcribe.py omit language_code so Scribe detects whatever
-- is spoken; matches the form's Auto-detect default.
if not lang_code or lang_code == "" then lang_code = "auto" end
if not diarize  or diarize  == "" then diarize  = "0" end
if not min_secs or min_secs == "" then min_secs = "0" end
if not cps      or cps      == "" then cps      = "0" end
if not text_size  or text_size  == "" then text_size  = "" end
if not outline    or outline    == "" then outline    = "1" end
if not shadow     or shadow     == "" then shadow     = "1" end
if not action     or action     == "" then action     = "generate" end
if not srt_input_path then srt_input_path = "" end
-- Empty means the loader could not work out the frame height, so posY stays
-- whatever subtitle_style.json says.
if not srt_posy then srt_posy = "" end
if not srt_fonts then srt_fonts = "" end
if not font_style or font_style == "" then font_style = "Auto" end
if not cap_font  then cap_font  = "" end
if not cap_color then cap_color = "" end
if not words_per or words_per == "" then words_per = "0" end
if not ref_script then ref_script = "" end
-- "Auto" font means keep the script-aware choice; treat as no override.
local font_override = (cap_font ~= "" and cap_font ~= "Auto (by language)") and cap_font or nil
-- Weight/style override ("Medium", "Bold", ...). "Auto" keeps defaults.
local style_override = (font_style ~= "Auto") and font_style or nil

-- Small hex -> r,g,b (0-1) helper available everywhere (there is also a
-- table-returning hex_to_rgb later, used by the caption styling).
local function hex_rgb3(h)
    local r, g, b = tostring(h):match("^#?(%x%x)(%x%x)(%x%x)$")
    if not r then return nil end
    return tonumber(r, 16) / 255, tonumber(g, 16) / 255, tonumber(b, 16) / 255
end
log("Language code: " .. lang_code .. "  diarize=" .. diarize
    .. " min_secs=" .. min_secs .. " cps=" .. cps)

-- ── Undo mode: remove the track the last generation created ────────────
-- Reads logs/last_gen.txt ("<video|subtitle> <trackIndex> <timelineName>").
-- Only removes the track if it belongs to the current timeline, so we never
-- delete something on a different timeline the user has since switched to.
if action == "undo" then
    local msg
    local lf = io.open(lastGenPath, "r")
    if not lf then
        msg = "Nothing to undo — no caption track has been generated yet."
    else
        local body = lf:read("*a") or ""; lf:close()
        local ttype, tidx, tname = body:match("(%S+)%s+(%d+)%s+(.-)%s*$")
        tidx = tonumber(tidx)
        if not ttype or not tidx then
            msg = "Nothing to undo — the undo record is empty or unreadable."
        elseif tname and tname ~= "" and tname ~= timeline:GetName() then
            msg = "Last captions were made on timeline \"" .. tname
                .. "\".\nSwitch to that timeline, then Undo again."
        else
            local ok = pcall(function()
                if tidx >= 1 and tidx <= timeline:GetTrackCount(ttype) then
                    timeline:DeleteTrack(ttype, tidx)
                end
            end)
            if ok then
                os.remove(lastGenPath)
                pm:SaveProject()
                msg = "Removed the last generated caption track ("
                    .. ttype .. " track " .. tidx .. ").\nProject saved."
            else
                msg = "Could not remove the caption track — it may have been "
                    .. "deleted or moved already."
            end
        end
    end
    log("Undo mode: " .. msg:gsub("\n", " | "))
    local rw = io.open(resultPath, "w")
    if rw then rw:write(msg); rw:close() end
    wait_for_ack()
    cleanup_run()
    return
end

local trackIndex = tonumber(chosen:match("^Track (%d+)")) or 1
log("Selected track index: " .. trackIndex)

local clips = timeline:GetItemListInTrack("audio", trackIndex)
if not clips or #clips == 0 then
    alert_error("Srutilekha", "No clips on the selected audio track.")
    return
end

-- Collect clip ranges for timeline remapping (Windows sync fix).
-- Each clip records its own source file path so correction clips (re-takes from
-- a different file dropped on the same track) are transcribed too, not skipped.
local fps     = tonumber(timeline:GetSetting("timelineFrameRate")) or 24
local tlStart = timeline:GetStartFrame()
-- Compute timecode string for SetCurrentTimecode (needed to anchor SRT import).
--
-- Timecode counts at the NOMINAL rate, never the real one: frame 86400 on a
-- 23.976 timeline is 01:00:00:00, not the 01:00:03:24 that dividing by 23.976
-- gives. Using `fps` here left `tlFr` fractional (86400 % 23.976 = 24.9), which
-- %02d then truncated, and the anchor landed ~86 frames off on every NTSC
-- timeline. Integer rates are unaffected — 24, 25, 30 round to themselves.
local tcFps = math.max(1, math.floor(fps + 0.5))
local tlFr  = tlStart % tcFps
local tlSec = math.floor(tlStart / tcFps)
local tc    = string.format("%02d:%02d:%02d:%02d",
                  math.floor(tlSec / 3600), math.floor((tlSec / 60) % 60), tlSec % 60, tlFr)
-- rangesPath is declared with the other per-run handshake files near the top.
local rf = io.open(rangesPath, "w")
local rangeCount = 0
local audioPath = ""
if rf then
    for _, c in ipairs(clips) do
        local cmpi = c:GetMediaPoolItem()
        if not cmpi then
            log("Skipping clip with no media pool item")
        else
            local cpath = (cmpi:GetClipProperty() or {})["File Path"] or ""
            if cpath == "" then
                log("Skipping clip with no source file path")
            else
                local srcStart = c:GetLeftOffset()
                local cTlStart = c:GetStart()
                local cTlEnd   = c:GetEnd()
                local tlFrames = cTlEnd - cTlStart
                local speed    = (c.GetPlayBackSpeed and c:GetPlayBackSpeed()) or 1.0
                if not speed or speed == 0 then speed = 1.0 end
                -- A reversed clip reports a negative speed, which made srcEnd
                -- land BEFORE srcStart. transcribe.py selects words with
                -- src_start <= t < src_end, so an inverted window matched
                -- nothing and the clip silently got no subtitles at all. Use the
                -- magnitude: the source region covered is the same either way
                -- (the words' order within it is a separate problem, and one this
                -- pipeline cannot solve by reversing timestamps).
                local span = math.floor(math.abs(tlFrames * speed) + 0.5)
                if speed < 0 then
                    log(string.format("Clip at frame %d is reversed (speed %.3f)"
                        .. " — transcribing its source range, but cue order"
                        .. " inside it will follow the source, not the reverse.",
                        cTlStart, speed))
                end
                local srcEnd = srcStart + math.max(1, span)
                rf:write(string.format("%d %d %d %g %d %s\n",
                    srcStart, srcEnd, cTlStart, fps, tlStart, cpath))
                rangeCount = rangeCount + 1
                if audioPath == "" then audioPath = cpath end
            end
        end
    end
    rf:close()
end
if rangeCount == 0 then
    alert_error("Srutilekha", "No clips on the selected track have a usable source file.")
    cleanup_run()
    return
end
log("Audio file (primary): " .. audioPath)
log(string.format("Mapped %d clip range(s); anchor=frame %d", rangeCount, tlStart))

-- ── Importing an SRT without destroying anything ────────────────────────────
-- This used to be three lines:
--
--     for i = timeline:GetTrackCount("subtitle"), 1, -1 do
--         timeline:DeleteTrack("subtitle", i)
--     end
--     timeline:AddTrack("subtitle")
--
-- i.e. every generation and every sync silently deleted EVERY subtitle track on
-- the timeline -- hand-authored subtitles, a forced-narrative track, an earlier
-- language pass, all of it, with no warning and nothing recorded for Undo. The
-- only reason it was there is that the code afterwards wanted the imported cues
-- to be on a known track index, and wiping the timeline made that index 1.
--
-- Instead: add a track, import, then find out where the cues actually landed by
-- diffing the subtitle tracks. Nothing is deleted, and the answer is observed
-- rather than assumed. Returns ok, trackIndex, items, createdTrack.
--
-- `items` is only the cues THIS import added, which is not the same as the
-- contents of the track they landed on. Resolve picks the track itself, and it
-- will happily append onto one that already holds an earlier run's subtitles:
-- on 2026-08-07 a 57-cue run landed on the track a 36-cue run had used and the
-- old code returned all 93. That reported "Imported 92 subtitle cues" for 57,
-- and — worse — ran the styling pass over the earlier run's cues, re-fonting
-- and re-colouring subtitles the user had never asked to touch.
local function import_srt_to_new_track(mp, srt_file)
    local function item_start(item)
        local ok, f = pcall(function() return item:GetStart() end)
        if ok then return f end
        return nil
    end

    -- Per-track set of occupied start frames. A start frame identifies a cue
    -- well enough for this: cues on one subtitle track cannot overlap, so no
    -- two of them share one.
    local function snapshot()
        local s = {}
        for i = 1, timeline:GetTrackCount("subtitle") do
            local seen = {}
            for _, item in ipairs(timeline:GetItemListInTrack("subtitle", i) or {}) do
                local f = item_start(item)
                if f then seen[f] = true end
            end
            s[i] = seen
        end
        return s
    end

    local before = snapshot()
    local beforeTracks = timeline:GetTrackCount("subtitle")
    -- A fresh empty track for the import to land on. Resolve gives no way to
    -- nominate a subtitle track, but an empty one at the end is where it puts an
    -- appended subtitle clip in practice; if it chooses elsewhere, the diff
    -- below still finds it.
    local addedTrack = nil
    if pcall(function() return timeline:AddTrack("subtitle") end)
            and timeline:GetTrackCount("subtitle") > beforeTracks then
        addedTrack = timeline:GetTrackCount("subtitle")
    end
    timeline:SetCurrentTimecode(tc)   -- anchor so SRT times align with timeline start

    local imported = mp:ImportMedia({srt_file})
    if not imported or #imported == 0 then
        if addedTrack then pcall(function() timeline:DeleteTrack("subtitle", addedTrack) end) end
        return false, nil, nil, false, "Resolve could not import the SRT file."
    end
    if not mp:AppendToTimeline({imported[1]}) then
        if addedTrack then pcall(function() timeline:DeleteTrack("subtitle", addedTrack) end) end
        return false, nil, nil, false, "Resolve could not append the SRT to the timeline."
    end

    -- Which track grew, and by which items? Both answers come from the same
    -- pass: an item at a start frame that was not occupied before this import
    -- is one of ours. Items stay in timeline order, so items[1] is the first
    -- cue of this run.
    local landed, newItems, priorCount = nil, {}, 0
    for i = 1, timeline:GetTrackCount("subtitle") do
        local prior = before[i] or {}
        local added = {}
        for _, item in ipairs(timeline:GetItemListInTrack("subtitle", i) or {}) do
            local f = item_start(item)
            -- No readable start frame: treat as ours. Leaving a cue of this
            -- run unstyled is worse than the unlikely alternative, and a
            -- handle that cannot answer GetStart is broken anyway.
            if not f or not prior[f] then added[#added + 1] = item end
        end
        if #added > #newItems then
            landed, newItems = i, added
            local n = 0
            for _ in pairs(prior) do n = n + 1 end
            priorCount = n
        end
    end
    if not landed then
        if addedTrack then pcall(function() timeline:DeleteTrack("subtitle", addedTrack) end) end
        return false, nil, nil, false,
            "The SRT imported but Resolve placed no cues on any subtitle track."
    end
    log(string.format("SRT cues landed on subtitle track %d: %d new, "
        .. "%d cue(s) already there (left untouched).",
        landed, #newItems, priorCount))

    -- If the cues went somewhere other than the track we made, drop ours again
    -- rather than leaving an empty track behind -- and do NOT claim it for Undo,
    -- because that track is the user's, not ours.
    local created = (addedTrack ~= nil and landed == addedTrack)
    if addedTrack and not created
            and #(timeline:GetItemListInTrack("subtitle", addedTrack) or {}) == 0 then
        pcall(function() timeline:DeleteTrack("subtitle", addedTrack) end)
    end
    return true, landed, newItems, created, nil
end

-- How many of these cues are the user's.
--
-- to_srt() writes a blank cue at t=0 so Resolve pins the imported clip to the
-- timeline start. It is not a subtitle anyone asked for, so it must not be
-- counted — but subtracting a fixed 1 for it was wrong, because Resolve DROPS
-- it on import rather than keeping it. Verified across the eight clean runs in
-- the log: a 36-segment sidecar yields exactly 36 items, never 37, so every run
-- reported one cue fewer than it produced. Counting the cues that carry text is
-- correct whether Resolve keeps the anchor or discards it.
local function count_real_cues(items)
    local n = 0
    for _, item in ipairs(items or {}) do
        if (item:GetName() or ""):match("%S") then n = n + 1 end
    end
    return n
end

-- Remember the track for Undo only when we created it ourselves. Undo deletes a
-- whole track, so pointing it at a track that already held the user's cues
-- would turn "undo my captions" into "delete my subtitles".
local function record_undo(kind, idx, created)
    if created then
        local gf = io.open(lastGenPath, "w")
        if gf then
            gf:write(string.format("%s %d %s", kind, idx, timeline:GetName()))
            gf:close()
        end
    else
        os.remove(lastGenPath)
    end
end

-- ── Sync mode: re-time an existing SRT against this audio, text unchanged ──
-- v1 scope: single audio track (no multi-clip retake remapping), no per-
-- speaker/font styling — the original SRT's formatting is left as-is, only
-- start/end times change. Reuses the same args-file/donePath/resultPath
-- plumbing as Generate (loader.pyw is already running and polling argsPath).
if action == "sync" then
    if srt_input_path == "" then
        alert_error("Srutilekha", "No existing SRT path was given to sync.")
        return
    end
    local srtInputCheck = io.open(srt_input_path, "rb")
    if not srtInputCheck then
        alert_error("Srutilekha", "Cannot read the existing SRT file:\n" .. srt_input_path)
        return
    end
    srtInputCheck:close()

    local srtOutPath = os.tmpname() .. ".srt"
    log("Sync mode: re-timing " .. srt_input_path .. " against " .. audioPath)

    local af = io.open(argsPath, "wb")
    if not af then
        alert_error("Srutilekha", "Cannot write args file: " .. argsPath)
        return
    end
    af:write("SYNC\n", audioPath, "\n", srt_input_path, "\n", srtOutPath, "\n",
             lang_code, "\n", diarize, "\n")
    af:close()

    local code, why = wait_for_done()
    os.remove(donePath)
    if code == nil then
        log("Sync abandoned (" .. tostring(why) .. ") — no captions applied.")
        if why == "timeout" then
            alert_error("Srutilekha",
                "The Srutilekha window stopped responding, so nothing was "
                .. "changed on the timeline.\n\nRun the script again.")
        end
        cleanup_run()
        return
    end

    if code == 130 then
        log("User cancelled sync (code 130) — no captions applied.")
        cleanup_run()
        return
    end
    if code ~= 0 then
        local errFile = io.open(LOG_FILE .. ".transcribe")
        local errMsg  = errFile and errFile:read("*a") or "Unknown error"
        if errFile then errFile:close() end
        alert_error("Srutilekha - Sync failed", errMsg:sub(1, 400))
        return
    end

    local check = io.open(srtOutPath)
    if not check then
        alert_error("Srutilekha", "Sync produced no output. Check:\n" .. LOG_FILE .. ".transcribe")
        return
    end
    check:close()

    local mp = project:GetMediaPool()
    local ok, strack, items, created, ierr =
        import_srt_to_new_track(mp, srtOutPath)
    os.remove(srtOutPath)
    if not ok then
        alert_error("Srutilekha", ierr or "Could not import the synced SRT.")
        cleanup_run()
        return
    end
    record_undo("subtitle", strack, created)

    local cueCount = count_real_cues(items)
    pm:SaveProject()
    log("Sync done. Re-timed and imported " .. cueCount
        .. " subtitle cues on subtitle track " .. strack .. ".")

    local result_msg = cueCount .. " subtitle cues re-timed and imported on "
        .. (created and "a new" or "existing") .. " subtitle track " .. strack .. "."
        .. "\n\nTimeline: " .. timeline:GetName() .. "\nProject saved."
    local rw = io.open(resultPath, "w")
    if rw then rw:write(result_msg); rw:close() end

    wait_for_ack()
    os.remove(resultPath)
    cleanup_run()
    return
end

-- Split "settings" POSITIONALLY. The old pattern was gmatch("[^,]+"), which
-- skips empty fields rather than yielding them: "25,,2" came out as {"25","2"},
-- so a cleared "Lines per cue" box silently became maxLines=2 and maxSecs=1 (the
-- fallback) instead of the values on screen. The loader now backfills blanks
-- before sending, but this side must not be the kind of parser that can shift
-- values either. Defaults match SETTINGS_DEFAULTS in loader.pyw.
local parts = {}
for p in tostring(settings or ""):gmatch("([^,]*),?") do
    if #parts >= 3 then break end
    parts[#parts + 1] = p:match("^%s*(.-)%s*$")
end
local function setting_at(i, default)
    local v = parts[i]
    if v == nil or v == "" then return default end
    return v
end
local maxChars = setting_at(1, "15")
local maxLines = setting_at(2, "1")
local maxSecs  = setting_at(3, "2")
log(string.format("Split settings: chars=%s lines=%s secs=%s (raw %q)",
    maxChars, maxLines, maxSecs, tostring(settings)))

local srtPath = os.tmpname() .. ".srt"
log("Transcribing...")

-- Write args as UTF-8 to a file so non-ASCII paths (e.g. curly apostrophes)
-- survive cmd.exe's codepage conversion on Windows. The loader is already
-- running (started above) and polling for this file — once written, it
-- spawns transcribe.py and updates its progress view in place.
local af = io.open(argsPath, "wb")
if not af then
    alert_error("Srutilekha", "Cannot write args file: " .. argsPath)
    return
end
af:write(audioPath, "\n", srtPath, "\n",
         maxChars, "\n", maxLines, "\n", maxSecs, "\n",
         rangesPath, "\n", include_punct, "\n", lang_code, "\n",
         diarize, "\n", cps, "\n", min_secs, "\n",
         words_per, "\n", ref_script, "\n")
af:close()
if ref_script ~= "" then log("Reference script: " .. ref_script) end

-- Poll the sentinel file the loader writes on completion.
local code, doneWhy = wait_for_done()
os.remove(donePath)
if code == nil then
    -- The loader is gone without reporting. Say so rather than hanging, and
    -- clear this run's scratch files on the way out.
    log("Run abandoned (" .. tostring(doneWhy) .. ") — no captions applied.")
    if doneWhy == "timeout" then
        alert_error("Srutilekha",
            "The Srutilekha window stopped responding, so nothing was changed "
            .. "on the timeline.\n\nRun the script again.")
    end
    cleanup_run()
    return
end

-- 130 = user cancelled (closed the window or cancelled at the review step).
-- Not an error: just stop quietly without the transcription-failed alert.
if code == 130 then
    log("User cancelled (code 130) — no captions applied.")
    cleanup_run()
    return
end

local success = (code == 0)

if not success then
    local errFile = io.open(LOG_FILE .. ".transcribe")
    local logText = errFile and errFile:read("*a") or ""
    if errFile then errFile:close() end

    -- Show the ERROR line transcribe.py writes, not the head of the log. The
    -- log opens with PROGRESS/status lines, so taking the first 400 characters
    -- showed the startup chatter and cut off before the actual cause.
    local errMsg = logText:match("\nERROR: (.*)$") or logText:match("^ERROR: (.*)$")
    if not errMsg or errMsg == "" then
        -- No tagged error (crash, or killed outright): fall back to the tail,
        -- which is where a traceback ends up.
        if #logText > 700 then
            errMsg = "…\n" .. logText:sub(-700)
        else
            errMsg = logText
        end
    end
    if not errMsg or errMsg:match("^%s*$") then
        errMsg = "Unknown error. Full log:\n" .. LOG_FILE .. ".transcribe"
    end
    alert_error("Srutilekha - Transcription failed",
                errMsg .. "\n\nFull log:\n" .. LOG_FILE .. ".transcribe")
    cleanup_run()
    return
end

local check = io.open(srtPath)
if not check then
    alert_error("Srutilekha", "Transcription produced no output.\n\nExpected: "
        .. srtPath .. "\nCheck:\n" .. LOG_FILE .. ".transcribe")
    cleanup_run()
    return
end
check:close()
log("SRT written to: " .. srtPath)

do
    local src = io.open(srtPath, "rb")
    if src then
        local content = src:read("*a"); src:close()
        local dbg = io.open(PROJECT_DIR .. SEP .. "logs" .. SEP .. "last.srt", "wb")
        if dbg then dbg:write(content); dbg:close() end
    end
    -- The .cap sidecar too: it is deleted with the SRT at the end of the run,
    -- and it — not the SRT — carries the per-speaker colours. Without a copy
    -- there is nothing left to inspect when the cues come out wrong.
    local csrc = io.open(srtPath .. ".cap", "rb")
    if csrc then
        local content = csrc:read("*a"); csrc:close()
        local dbg = io.open(PROJECT_DIR .. SEP .. "logs" .. SEP .. "last.srt.cap", "wb")
        if dbg then dbg:write(content); dbg:close() end
    end
end

local mp = project:GetMediaPool()

-- Devanagari (Hindi) detection on raw UTF-8 bytes — used by both caption
-- styles to pick the right font.
-- Core block U+0900–U+097F encodes as E0 A4 80 … E0 A5 BF. The danda ।
-- (U+0964 = E0 A5 A4) and double danda ॥ (U+0965 = E0 A5 A5) sit in this
-- block but are shared with Bengali, so they are explicitly skipped.
-- Devanagari Extended U+A8E0–U+A8FF encodes as EA A3 A0 … EA A3 BF.
-- ── Which script a cue is written in ────────────────────────────────────
-- Every Indic block this tool targets is three UTF-8 bytes starting E0, and the
-- SECOND byte alone identifies the block: U+0900-0D7F maps onto E0 A4 .. E0 B5
-- in pairs, one pair per script. Perso-Arabic (Urdu) is two bytes, D8-DB.
--
-- This replaces a Devanagari-only test. Every non-Devanagari cue used to fall
-- through to the single default font, so a Tamil or Telugu subtitle was set in
-- a Bengali serif that has none of its glyphs and rendered as empty boxes on
-- the timeline.
local SCRIPT_BY_B2 = {
    [0xA4] = "deva", [0xA5] = "deva",
    [0xA6] = "beng", [0xA7] = "beng",   -- Bengali and Assamese share the block
    [0xA8] = "guru", [0xA9] = "guru",
    [0xAA] = "gujr", [0xAB] = "gujr",
    [0xAC] = "orya", [0xAD] = "orya",
    [0xAE] = "taml", [0xAF] = "taml",
    [0xB0] = "telu", [0xB1] = "telu",
    [0xB2] = "knda", [0xB3] = "knda",
    [0xB4] = "mlym", [0xB5] = "mlym",
}

-- The script the majority of a cue's letters are in, or nil for Latin/none.
-- Counted rather than first-match because the danda (U+0964/0965) lives in the
-- Devanagari block but is punctuation for every Indic script — a Tamil cue
-- ending in one would otherwise be typeset in a Devanagari font. For the same
-- reason the danda itself is never counted.
local function script_of(s)
    if not s or s == "" then return nil end
    local counts, best, bestN = {}, nil, 0
    local i, n = 1, #s
    while i <= n do
        local b1 = s:byte(i)
        local tag, width = nil, 1
        if b1 == 0xE0 and i + 2 <= n then
            local b2, b3 = s:byte(i + 1), s:byte(i + 2)
            width = 3
            if not (b2 == 0xA5 and (b3 == 0xA4 or b3 == 0xA5)) then
                tag = SCRIPT_BY_B2[b2]
            end
        elseif b1 == 0xEA and i + 2 <= n then
            local b2, b3 = s:byte(i + 1), s:byte(i + 2)
            width = 3
            if b2 == 0xA3 and b3 >= 0xA0 and b3 <= 0xBF then
                tag = "deva"            -- Devanagari Extended
            end
        elseif b1 >= 0xD8 and b1 <= 0xDB and i + 1 <= n then
            tag, width = "arab", 2
        elseif b1 >= 0xF0 then
            width = 4
        elseif b1 >= 0xE0 then
            width = 3
        elseif b1 >= 0xC0 then
            width = 2
        end
        if tag then
            local c = (counts[tag] or 0) + 1
            counts[tag] = c
            if c > bestN then best, bestN = tag, c end
        end
        i = i + width
    end
    return best
end

-- "  (12 deva -> Vesper Libre, 4 taml -> Nirmala UI)" for the completion log,
-- so a wrong font is visible in the log rather than only on the timeline.
local function script_summary(counts, fonts)
    local parts = {}
    for tag, n in pairs(counts) do
        parts[#parts + 1] = string.format("%d %s -> %s", n, tag,
                                          tostring(fonts[tag] or "?"))
    end
    if #parts == 0 then return "" end
    table.sort(parts)
    return "  (" .. table.concat(parts, ", ") .. ")"
end

-- script tag -> font family, as resolved by the loader against the fonts
-- actually installed on this machine.
local scriptFonts = {}
for tag, fam in tostring(srt_fonts):gmatch("([%a]+)=([^|]+)") do
    scriptFonts[tag] = fam
end

-- The font one cue should be set in. An explicit choice in the form always
-- wins; otherwise the cue's own script decides, and only a cue in no script we
-- know about falls back to the default.
local function font_for(text, override, deva_font, default_font)
    if override and override ~= "" then return override end
    local tag = script_of(text)
    if tag then
        if scriptFonts[tag] and scriptFonts[tag] ~= "" then
            return scriptFonts[tag]
        end
        -- No map (an older loader) — the one script that had its own font
        -- before this existed still gets it.
        if tag == "deva" and deva_font then return deva_font end
    end
    return default_font
end

-- Subtitle styling comes from subtitle_style.json so it can be changed
-- without editing this script. "fontFace" is the default font and
-- "fontFaceDevanagari" is used for Hindi/Devanagari cues (one font per cue).
-- Unknown/nested keys (strokeColor's r/g/b/a) are skipped. Falls back to the
-- historical hardcoded style when the JSON is missing or unreadable.
local function load_style()
    local f = io.open(PROJECT_DIR .. SEP .. "subtitle_style.json")
    if not f then return nil end
    local body = f:read("*a"); f:close()
    if not body or body == "" then return nil end
    local style = {}
    for k, v in body:gmatch('"([%w_]+)"%s*:%s*"(.-)"') do style[k] = v end
    for k, v in body:gmatch('"([%w_]+)"%s*:%s*(-?%d+%.?%d*)') do
        if style[k] == nil then style[k] = tonumber(v) end
    end
    return style
end

local style = load_style() or {
    fontFace = "Noto Serif Bengali", fontFaceDevanagari = "Vesper Libre",
    bold = 1, fontSize = 55, strokeEnabled = 1, strokeOutsideOnly = 1,
    customPosition = 1, posY = 620, shadowEnabled = 1,
    shadowXOffset = 3, shadowYOffset = 3, shadowOpacity = 100,
}
local defFont = style.fontFace or "Noto Serif Bengali"
local devFont = style.fontFaceDevanagari or "Vesper Libre"
local skipKeys = { fontFace = true, fontFaceDevanagari = true,
                   strokeColor = true, r = true, g = true, b = true, a = true }

-- ── Caption sidecar (per-word timing + per-speaker colour) ──────────────
-- transcribe.py writes "<srt>.cap" next to the SRT in a simple line format so
-- no JSON parser is needed here:
--   FPS <rate>
--   SPK <idx> <#hex> <style>        (1-based speaker, in appearance order)
--   SEG <start_s> <end_s> <spkIdx>  (times are timeline-relative seconds)
--   WRD <start_s> <end_s> <word>    (words follow their SEG; spkIdx 0 = none)
local capPath = srtPath .. ".cap"
local caption = { fps = fps, speakers = {}, segments = {} }
do
    local cf = io.open(capPath, "rb")
    if cf then
        local curSeg = nil
        for rawline in cf:lines() do
            local ln = rawline:gsub("\r$", "")
            local tag = ln:match("^(%u+)")
            if tag == "FPS" then
                caption.fps = tonumber(ln:match("^FPS%s+([%d%.]+)")) or fps
            elseif tag == "SPK" then
                local idx, hex, sstyle = ln:match("^SPK%s+(%d+)%s+(%S+)%s+(%S+)")
                if idx then
                    caption.speakers[tonumber(idx)] = { hex = hex, style = sstyle or "Fill" }
                end
            elseif tag == "SEG" then
                local s, e, spk = ln:match("^SEG%s+(%-?[%d%.]+)%s+(%-?[%d%.]+)%s+(%d+)")
                if s then
                    curSeg = { start = tonumber(s), endt = tonumber(e),
                               spk = tonumber(spk) or 0, words = {} }
                    table.insert(caption.segments, curSeg)
                end
            elseif tag == "WRD" and curSeg then
                local s, e, w = ln:match("^WRD%s+(%-?[%d%.]+)%s+(%-?[%d%.]+)%s+(.*)$")
                if s then
                    table.insert(curSeg.words,
                        { start = tonumber(s), endt = tonumber(e), word = w })
                end
            end
        end
        cf:close()
        -- A segment that parsed without any WRD line has lost its word
        -- timings, which is worth saying here, where the numbers are still in
        -- front of us.
        local wordTotal, wordless = 0, 0
        for _, sg in ipairs(caption.segments) do
            wordTotal = wordTotal + #sg.words
            if #sg.words == 0 then wordless = wordless + 1 end
        end
        log(string.format("Caption sidecar: %d segment(s), %d word(s)%s",
            #caption.segments, wordTotal,
            wordless > 0 and (" — " .. wordless .. " with NO words (blank captions)") or ""))
    else
        log("Caption sidecar missing: " .. capPath)
    end
end

local function hex_to_rgb(hex)
    local r, g, b = tostring(hex):match("^#?(%x%x)(%x%x)(%x%x)$")
    if not r then return nil end
    return { r = tonumber(r, 16) / 255, g = tonumber(g, 16) / 255, b = tonumber(b, 16) / 255 }
end

-- Speaker index -> subtitle-item colour, as a nested {r,g,b,a} table in 0-1
-- range (same shape as strokeColor in subtitle_style.json). nil when unknown.
local function speaker_color(spk)
    if not spk or spk == 0 then return nil end
    local sp = caption.speakers[spk]
    if not sp then return nil end
    local rgb = hex_to_rgb(sp.hex)
    if not rgb then return nil end
    return { r = rgb.r, g = rgb.g, b = rgb.b, a = 1 }
end

-- Match a subtitle item to its caption segment by nearest start time (the
-- subtitle track carries a dummy blank cue at t=0, so index alignment is not
-- reliable). Times are timeline-relative seconds.
local function segment_for_time(sec)
    local best, bestDelta = nil, 0.30
    for _, seg in ipairs(caption.segments) do
        local d = math.abs(seg.start - sec)
        if d <= bestDelta then best, bestDelta = seg, d end
    end
    return best
end

-- ── Import onto a new subtitle track ─────────────────────────────────
-- Existing subtitle tracks are left alone; see import_srt_to_new_track.
local count = 0
local scriptCounts, fontUsed = {}, {}

local ok, strack, items, created, ierr = import_srt_to_new_track(mp, srtPath)
os.remove(srtPath); os.remove(capPath)
if not ok then
    alert_error("Srutilekha", ierr or "Could not import the SRT file.")
    cleanup_run()
    return
end
local subtitleTrack = strack
record_undo("subtitle", strack, created)

-- Any blank anchor cue that did survive is still styled below, so it stays
-- invisible rather than becoming a differently-fonted blank frame.
count = count_real_cues(items)

-- Where the first cue landed. This used to compare against tlStart and
-- report a "delta" of 3-6 frames on every healthy run, which reads as a
-- broken anchor and is not one: the anchor cue is gone, so the first item
-- is the first REAL cue, and it belongs at the frame its own timestamp
-- says. Compare against that instead, so a non-zero delta means something.
if items[1] then
    local first = caption.segments[1]
    local want = tlStart + (first and math.floor(first.start * fps) or 0)
    local got  = items[1]:GetStart()
    log(string.format("First SRT cue at frame %d (expected %d, delta %d)",
        got, want, got - want))
end

-- The user's font/colour/stroke/shadow/weight choices, applied to the
-- subtitle cues.
for _, item in ipairs(items) do
    local text = item:GetName() or ""
    -- One font per cue, chosen by the script the cue is written in, so a
    -- mixed-language timeline sets each subtitle in a family that has its
    -- glyphs instead of putting everything but Devanagari in one default.
    local fam = font_for(text, font_override, devFont, defFont)
    item:SetProperty("fontFace", fam)
    local tag = script_of(text)
    if tag then
        scriptCounts[tag] = (scriptCounts[tag] or 0) + 1
        fontUsed[tag] = fam
    end
    for k, v in pairs(style) do
        if not skipKeys[k] then item:SetProperty(k, v) end
    end
    -- User style overrides from the dialog: text size + outline/shadow.
    local ts = tonumber(text_size)
    if ts and ts > 0 then item:SetProperty("fontSize", ts) end
    -- Where the cue sits. The loader sends this already converted to
    -- pixels for this timeline's height, because it is the side that knows
    -- both the fraction the user picked and the frame it was picked
    -- against. A reel needs the text much higher than an HD cut does, so a
    -- single hardcoded posY cannot serve both.
    local py = tonumber(srt_posy)
    if py and py > 0 then
        item:SetProperty("customPosition", 1)
        item:SetProperty("posY", py)
    end
    item:SetProperty("strokeEnabled", (outline == "1") and 1 or 0)
    item:SetProperty("shadowEnabled", (shadow == "1") and 1 or 0)
    -- Weight/style: subtitle items only expose bold/italic flags, so map
    -- the chosen weight onto those ("Medium"/"Light" -> regular weight).
    if style_override then
        local lsty = style_override:lower()
        item:SetProperty("bold",   lsty:find("bold")   and 1 or 0)
        item:SetProperty("italic", lsty:find("italic") and 1 or 0)
    end
    -- Colour: a manual dialog colour applies to every cue; otherwise fall
    -- back to the per-speaker colour matched by time.
    local col = nil
    if cap_color ~= "" then
        local r, g, b = hex_rgb3(cap_color)
        if r then col = { r = r, g = g, b = b, a = 1 } end
    else
        local sec = (item:GetStart() - tlStart) / fps
        local seg = segment_for_time(sec)
        col = speaker_color(seg and seg.spk or 0)
    end
    if col then pcall(function() item:SetProperty("color", col) end) end
end

pm:SaveProject()
log("Done. Imported " .. count .. " subtitle cues" .. script_summary(scriptCounts, fontUsed) .. ".")

-- Write completion message for the loader window to display in-place,
-- then wait for the user to click OK before exiting.
local result_msg = count .. " subtitle cues imported"
    .. (subtitleTrack and (" on subtitle track " .. subtitleTrack) or "") .. "."
    .. "\n\nTimeline: " .. timeline:GetName() .. "\nProject saved."
local rw = io.open(resultPath, "w")
if rw then rw:write(result_msg); rw:close() end

wait_for_ack()
cleanup_run()
