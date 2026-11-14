-- Srutilekha local Lua bridge. Generated launcher supplies the mailbox path.
-- No io, ffi, package, require, os.execute or external Python scripting.
local mailbox = "__SRUTILEKHA_MAILBOX__"
local prefs = fusion or fu
local rv = resolve or (prefs and prefs:GetResolve())
local function has_method(object, name)
    local ok, value = pcall(function() return object[name] end)
    return ok and type(value) == 'function'
end
-- Resolve 21.2 removed loadfile, dofile and SavePrefs, and only flushes
-- SetPrefs to disk every ~30 s. Fusion's FileIO (OpenFile/ReadLine/WriteLine)
-- still works, so requests and responses travel through mailbox files there.
local compile = loadstring or load
local can_open = prefs and has_method(prefs, 'OpenFile')
if not prefs or not rv or not bmd or not bmd.wait or not (loadfile or (can_open and compile)) then
    print("Srutilekha: this scripting host does not support the local bridge.")
    return
end
local function save_prefs()
    if has_method(prefs, 'SavePrefs') then prefs:SavePrefs() end
end
local function write_file(name, body)
    if not can_open then return false end
    local ok = pcall(function()
        local file = prefs:OpenFile(mailbox .. '/' .. name, 2)
        if not file then error('cannot open') end
        for i = 1, #body, 1000 do file:WriteLine(body:sub(i, i + 999)) end
        file:WriteLine('END')
        pcall(function() file:Flush() end)
        file:Close()
    end)
    return ok
end
local function read_request()
    local chunk
    if loadfile then
        chunk = loadfile(mailbox .. '/request.lua')
    else
        local file = prefs:OpenFile(mailbox .. '/request.lua', 1)
        if not file then return nil end
        local lines = {}
        local ok = pcall(function()
            while #lines < 100000 do
                local line = file:ReadLine()
                if line == nil then break end
                lines[#lines + 1] = line
            end
        end)
        pcall(function() file:Close() end)
        if not ok or #lines == 0 then return nil end
        chunk = compile(table.concat(lines, '\n'), '=request')
    end
    -- Requests are data-only table literals; give them no globals.
    if chunk and setfenv then setfenv(chunk, {}) end
    return chunk
end
local session = tostring({}):gsub("[^%w]", "") .. tostring(os.time())
local owner_key = "Global.SrutilekhaBridgeOwner"
local function announce(token)
    prefs:SetPrefs('Global.SrutilekhaBridgeLaunch', token)
    prefs:SetPrefs('Global.SrutilekhaBridgeLaunchTime', os.time())
    save_prefs()
    write_file('launch.txt', token .. ' ' .. tostring(os.time()))
end
local existing = prefs:GetPrefs(owner_key)
if existing and existing ~= '' then
    prefs:SetPrefs('Global.SrutilekhaBridgeProbe', session)
    for i=1,10 do
        bmd.wait(.1)
        if prefs:GetPrefs('Global.SrutilekhaBridgeProbeAck') == session then
            announce(session)
            print('Srutilekha: opening captions through the tray helper.')
            return
        end
    end
end
prefs:SetPrefs(owner_key, session)
local refs, ids, next_ref = {}, {}, 0
local function register(value)
    if ids[value] then return ids[value] end
    next_ref = next_ref+1; refs[next_ref]=value; ids[value]=next_ref
    return next_ref
end
local resolve_ref = register(rv)
local allowed = {}
for name in string.gmatch([[GetVersionString GetProductName GetCurrentPage OpenPage GetProjectManager
GetCurrentProject GetMediaPool GetCurrentTimeline GetName GetSetting GetStartFrame
GetTrackCount GetTrackName GetItemListInTrack GetMediaPoolItem GetClipProperty
GetLeftOffset GetStart GetEnd GetPlayBackSpeed GetUniqueId GetTrackEnable SetTrackEnable
GetTrackLock SetTrackLock GetIsTrackLocked GetIsTrackEnabled GetCurrentTimecode SetCurrentTimecode AddTrack DeleteTrack
ImportMedia AppendToTimeline DeleteClips SetProperty GetProperty SetName SaveProject
SetProperties GetProperties GetSpeed
GetRootFolder GetCurrentFolder SetCurrentFolder GetClipList GetSubFolderList
GetTimelineCount GetTimelineByIndex SetCurrentTimeline GetProjectListInCurrentFolder
GetCurrentDatabase CreateProject CloseProject LoadProject CreateEmptyTimeline]], "%S+") do allowed[name]=true end
local function quote(s)
    return '"' .. tostring(s):gsub('[%z\1-\31\\"]', function(c)
        if c=='"' then return '\\"' elseif c=='\\' then return '\\\\' end
        return string.format('\\u%04x',string.byte(c))
    end) .. '"'
end
local function json(value, depth)
    depth=(depth or 0)+1
    if depth>30 then error("Bridge value is too deeply nested") end
    local t=type(value)
    if t=='nil' then return 'null' end
    if t=='boolean' or t=='number' then return tostring(value) end
    if t=='string' then return quote(value) end
    if t=='userdata' then return '{"__ref":'..register(value)..'}' end
    if t~='table' then error('Unsupported API result: '..t) end
    if getmetatable(value) and type(value.GetName)=='function' then return '{"__ref":'..register(value)..'}' end
    local out, count, is_array = {}, 0, true
    for k in pairs(value) do
        if k~='__flags' then
            count=count+1; if type(k)~='number' or k<1 or k%1~=0 then is_array=false end
        end
    end
    if count~=#value then is_array=false end
    if is_array and count>0 then
        for i=1,#value do out[#out+1]=json(value[i],depth) end
        return '['..table.concat(out,',')..']'
    end
    for k,v in pairs(value) do
        if k~='__flags' then out[#out+1]=quote(k)..':'..json(v,depth) end
    end
    return '{'..table.concat(out,',')..'}'
end
local alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
local function base64(s)
    local out={}
    for i=1,#s,3 do
        local a,b,c=s:byte(i,i+2); b=b or 0; c=c or 0
        local n=a*65536+b*256+c
        out[#out+1]=alphabet:sub(math.floor(n/262144)%64+1,math.floor(n/262144)%64+1)
        out[#out+1]=alphabet:sub(math.floor(n/4096)%64+1,math.floor(n/4096)%64+1)
        out[#out+1]=i+1<=#s and alphabet:sub(math.floor(n/64)%64+1,math.floor(n/64)%64+1) or '='
        out[#out+1]=i+2<=#s and alphabet:sub(n%64+1,n%64+1) or '='
    end
    return table.concat(out)
end
local function unpack_value(value)
    if type(value)~='table' then return value end
    if value.__ref then
        if not refs[value.__ref] then error('Stale Resolve object; reconnect the app') end
        return refs[value.__ref]
    end
    local out={}; for k,v in pairs(value) do out[k]=unpack_value(v) end
    return out
end
local function dispatch(req)
    if req.protocol~=1 then error('Bridge protocol mismatch; update Srutilekha') end
    if req.op=='hello' then
        return {session=session,resolve=resolve_ref,version=rv:GetVersionString(),product=rv:GetProductName()}
    end
    if req.session~=session then error('Resolve bridge restarted; reconnect the app') end
    if req.op=='stop' then prefs:SetPrefs(owner_key, ''); return true end
    if req.op=='caption_info' then
        local out={}
        for _,id in ipairs(req.refs or {}) do
            local item=refs[id]; if not item then error('Stale caption object') end
            out[#out+1]={name=item:GetName(),start=item:GetStart()}
        end
        return out
    end
    if req.op=='batch' then
        if #req.calls>100 then error('Bridge batch is too large') end
        local out={}
        for _,call in ipairs(req.calls) do
            if call.method~='SetProperty' then error('Unsupported batch operation') end
            call.op='call';call.session=session;call.protocol=1
            out[#out+1]=dispatch(call) == true
        end
        return out
    end
    if req.op~='call' or not allowed[req.method] then error('Unsupported bridge method') end
    local target=refs[req.ref]
    if not target then error('Stale Resolve object; reconnect the app') end
    local args=unpack_value(req.args or {})
    -- Resolve 21.2 validates SetProperties keys against TimelineItemProperties,
    -- which lists no subtitle text styles, and GetProperties returns {} for
    -- subtitle cues. Fall back to the native per-key calls where they exist.
    if req.method=='SetProperty' then
        local ok,done=pcall(function() return target:SetProperties({[args[1]]=args[2]}) end)
        if ok and done then return true end
        if has_method(target,'SetProperty') then return target:SetProperty(args[1],args[2]) == true end
        return false
    elseif req.method=='GetProperty' then
        local ok,properties=pcall(function() return target:GetProperties() end)
        if not ok or type(properties)~='table' then properties={} end
        if not args[1] then return properties end
        if properties[args[1]]~=nil then return properties[args[1]] end
        if has_method(target,'GetProperty') then return target:GetProperty(args[1]) end
        return nil
    elseif req.method=='GetPlayBackSpeed' then
        local speed=target:GetSpeed()
        if type(speed)=='table' and type(speed.Percentage)=='number' then return speed.Percentage/100 end
        return 1.0
    end
    local method=target[req.method]
    if type(method)~='function' then error('Resolve API unavailable: '..req.method) end
    return method(target, unpack(args,1,req.argc or #args))
end
announce(session)
print('Srutilekha bridge ready. The tray helper will open captions automatically.')
local last_id=nil
local last_probe=nil
while prefs:GetPrefs(owner_key)==session do
    local probe=prefs:GetPrefs('Global.SrutilekhaBridgeProbe')
    if probe and probe~=last_probe then
        last_probe=probe
        prefs:SetPrefs('Global.SrutilekhaBridgeProbeAck', probe)
    end
    local read_ok,chunk=pcall(read_request)
    if read_ok and chunk then
        local ok,req=pcall(chunk)
        if ok and type(req)=='table' and type(req.id)=='string' and req.id:match('^%w+$') and req.id~=last_id then
            last_id=req.id
            local success,value=pcall(dispatch,req)
            local response=success and {ok=true,value=value} or {ok=false,error=tostring(value)}
            local packed_ok,body=pcall(json,response)
            if not packed_ok then body=json({ok=false,error='Cannot encode Resolve result: '..tostring(body)}) end
            local encoded=base64(body)
            write_file('response-'..req.id..'.txt', encoded)
            prefs:SetPrefs('Global.SrutilekhaBridgeResponse',req.id..':'..encoded)
            save_prefs()
        end
    end
    bmd.wait(.1)
end
