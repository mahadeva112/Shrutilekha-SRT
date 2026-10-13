"""Local request mailbox for Resolve's restricted Lua host; no Python API import."""
import base64
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid
from contextlib import contextmanager
from app_runtime import user_dir


class BridgeError(RuntimeError):
    pass


@contextmanager
def mailbox_lock(path, timeout=0):
    """Windows process lock; automatically released if the app exits."""
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if not path.stat().st_size:
            handle.write(b'0'); handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise BridgeError('Another Srutilekha operation is running. Close its caption window before connecting again.')
                time.sleep(.04)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def write_launcher(target, directory=None):
    from app_runtime import resources
    directory = Path(directory) if directory else user_dir() / 'resolve-bridge'
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    source = (resources() / 'resolve_bridge.lua').read_text(encoding='utf-8')
    Path(target).write_text(source.replace('"__SRUTILEKHA_MAILBOX__"', lua_value(str(directory))), encoding='utf-8')


def lua_value(value):
    """Encode only data, with unambiguous UTF-8 byte escapes in Lua strings."""
    if isinstance(value, RemoteObject):
        return '{["__ref"]=' + str(value.ref) + '}'
    if value is None:
        return 'nil'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError('Non-finite bridge number')
        return repr(value)
    if isinstance(value, str):
        return '"' + ''.join('\\%03d' % b for b in value.encode('utf-8')) + '"'
    if isinstance(value, (list, tuple)):
        return '{' + ','.join(lua_value(v) for v in value) + '}'
    if isinstance(value, dict):
        return '{' + ','.join('['+lua_value(k)+']='+lua_value(v) for k,v in value.items()) + '}'
    raise TypeError('Unsupported bridge value: '+type(value).__name__)


class RemoteObject:
    def __init__(self, client, ref):
        self.client, self.ref = client, ref

    def __getattr__(self, method):
        if method.startswith('_'):
            raise AttributeError(method)
        return lambda *args: self.client.call(self.ref, method, list(args))


class BridgeClient:
    def __init__(self, directory=None, prefs=None, timeout=20):
        self.directory = Path(directory) if directory else user_dir() / 'resolve-bridge'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.prefs = Path(prefs) if prefs else Path(os.environ['APPDATA']) / (
            'Blackmagic Design/DaVinci Resolve/Support/Fusion/Profiles/Default/Fusion.prefs')
        self.timeout = timeout
        self.lock = threading.Lock()
        self.session = None
        self.pending = None
        self.cache = {}
        self.rejected_style_properties = 0

    def _decode(self, value):
        if isinstance(value, dict):
            if set(value) == {'__ref'}:
                return RemoteObject(self, value['__ref'])
            return {k:self._decode(v) for k,v in value.items()}
        if isinstance(value, list):
            return [self._decode(v) for v in value]
        return value

    def request(self, payload):
        with self.lock, mailbox_lock(self.directory / 'request.lock', self.timeout):
            request_id = uuid.uuid4().hex
            payload = dict(payload, id=request_id, protocol=1)
            if self.session:
                payload['session'] = self.session
            request_path = self.directory / 'request.lua'
            scratch = self.directory / ('request-'+request_id+'.tmp')
            scratch.write_text('return '+lua_value(payload)+'\n', encoding='utf-8')
            os.replace(scratch, request_path)
            deadline = time.monotonic()+self.timeout
            try:
                while time.monotonic() < deadline:
                    try:
                        content = self.prefs.read_text(encoding='utf-8', errors='replace')
                    except OSError:
                        content = ''
                    match = re.search(r'SrutilekhaBridgeResponse\s*=\s*"'+request_id+r':([A-Za-z0-9+/=]+)"',content)
                    if match:
                        response = json.loads(base64.b64decode(match.group(1), validate=True))
                        if not response.get('ok'):
                            raise BridgeError(response.get('error','Resolve bridge request failed'))
                        return self._decode(response.get('value'))
                    time.sleep(.04)
                raise BridgeError('Resolve bridge is not responding. In Resolve, open Workspace > Scripts > Srutilekha, then try Connect again.')
            finally:
                # Do not leave a timed-out mutation to run after the user retries.
                try:
                    content = request_path.read_text(encoding='utf-8')
                    if request_id in content or lua_value(request_id) in content:
                        request_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def connect(self):
        self.session = None
        info = self.request({'op':'hello'})
        self.session = info['session']
        return info, RemoteObject(self, info['resolve'])

    def call(self, ref, method, args):
        if self.pending is not None and method == 'SetProperty':
            self.pending.append({'ref':ref,'method':method,'args':args,'argc':len(args)})
            if len(self.pending) >= 100:
                self.flush()
            return True
        if self.pending:
            self.flush()
        if not args and (ref, method) in self.cache:
            return self.cache[ref, method]
        return self.request({'op':'call','ref':ref,'method':method,'args':args,'argc':len(args)})

    def flush(self):
        if self.pending:
            calls, self.pending = self.pending, []
            results = self.request({'op':'batch','calls':calls})
            self.rejected_style_properties += sum(value is False for value in results)

    def style_items(self, function, items, *args, **kwargs):
        values = self.request({'op':'caption_info','refs':[item.ref for item in items]})
        for item, value in zip(items, values):
            self.cache[item.ref, 'GetName'] = value.get('name','')
            self.cache[item.ref, 'GetStart'] = value.get('start',0)
        self.pending = []
        try:
            result = function(items, *args, **kwargs)
            self.flush()
            if self.rejected_style_properties:
                import audio_to_srt
                audio_to_srt.log('Resolve did not accept %d style property writes; caption text and timings are retained.' % self.rejected_style_properties)
            return result
        finally:
            self.pending = None
            self.cache.clear()


def run_workflow():
    directory = user_dir() / 'resolve-bridge'
    with mailbox_lock(directory / 'workflow.lock'):
        _run_workflow()


def _run_workflow():
    """Use the existing orchestration and form through Lua object proxies."""
    client = BridgeClient()
    info, resolve = client.connect()
    import audio_to_srt
    audio_to_srt.resolve = resolve
    original_style = audio_to_srt.apply_styles
    audio_to_srt.apply_styles = lambda items,*a,**kw: client.style_items(original_style,items,*a,**kw)
    original_report = audio_to_srt.Run.report
    def report(run, text):
        if client.rejected_style_properties:
            text += '\n\nResolve did not accept some caption styling properties. Text and timing were imported; review the style in Resolve.'
        return original_report(run, text)
    audio_to_srt.Run.report = report
    audio_to_srt.main()
