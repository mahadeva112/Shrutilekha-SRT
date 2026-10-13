import base64
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from resolve_bridge import BridgeClient, BridgeError, RemoteObject, lua_value, mailbox_lock
import audio_to_srt as workflow

class BridgeTests(unittest.TestCase):
    def test_strings_are_only_byte_escapes(self):
        text='বাংলা "\\\nreturn os.execute("bad")'
        encoded=lua_value(text)
        self.assertEqual(encoded, '"'+''.join('\\%03d'%b for b in text.encode())+'"')
        with self.assertRaises(ValueError): lua_value(float('nan'))
        self.assertEqual(lua_value([None,True,2]),'{nil,true,2}')

    def test_protocol_roundtrip_errors_and_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); prefs=folder/'Fusion.prefs'
            client=BridgeClient(folder,prefs,.5)
            def respond(ok):
                deadline=time.monotonic()+1
                while not (folder/'request.lua').exists() and time.monotonic()<deadline: time.sleep(.005)
                payload={'ok':ok,'value':{'nested':[{'__ref':4}]},'error':'restarted'}
                prefs.write_text('SrutilekhaBridgeResponse = "fixed:'+base64.b64encode(json.dumps(payload).encode()).decode()+'"')
            for ok in (True,False):
                prefs.unlink(missing_ok=True)
                thread=threading.Thread(target=respond,args=(ok,));thread.start()
                with patch('resolve_bridge.uuid.uuid4',return_value=SimpleNamespace(hex='fixed')):
                    if ok:
                        result=client.request({'op':'hello'})
                        self.assertIsInstance(result['nested'][0],RemoteObject)
                        self.assertEqual(result['nested'][0].ref,4)
                    else:
                        with self.assertRaisesRegex(BridgeError,'restarted'):client.request({'op':'hello'})
                thread.join();self.assertFalse((folder/'request.lua').exists())
            prefs.unlink();client.timeout=.05
            with self.assertRaises(BridgeError):client.request({'op':'hello'})
            self.assertFalse((folder/'request.lua').exists())

    def test_two_process_clients_cannot_overlap_mailbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lock'
            with mailbox_lock(path):
                with self.assertRaises(BridgeError):
                    with mailbox_lock(path):pass
            with mailbox_lock(path):pass

    def test_style_batch_reports_rejected_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=BridgeClient(tmp,Path(tmp)/'prefs')
            client.pending=[]
            with patch.object(client,'request',return_value=[True,False]) as request:
                client.call(1,'SetProperty',['fontFace','Arial'])
                client.call(1,'SetProperty',['fontSize',24])
                client.flush()
            self.assertEqual(client.rejected_style_properties,1)
            self.assertEqual(len(request.call_args.args[0]['calls']),2)

    def test_clip_range_mapping_keeps_speed_and_source(self):
        clip=SimpleNamespace(GetMediaPoolItem=lambda:SimpleNamespace(GetClipProperty=lambda:{'File Path':'demo.wav'}),GetLeftOffset=lambda:24,GetStart=lambda:48,GetEnd=lambda:96,GetPlayBackSpeed=lambda:2)
        with tempfile.TemporaryDirectory() as tmp:
            run=SimpleNamespace(ranges=str(Path(tmp)/'ranges'))
            count,path=workflow.collect_clip_ranges(run,None,[clip],24,0)
            self.assertEqual((count,path),(1,'demo.wav'))
            self.assertEqual(Path(run.ranges).read_text().strip(),'24 120 48 24 0 demo.wav')

    def test_import_styles_only_new_cues_when_resolve_uses_old_track(self):
        old=SimpleNamespace(GetStart=lambda:0);new=SimpleNamespace(GetStart=lambda:24)
        tracks={1:[old]}
        def add(kind):tracks[2]=[];return True
        def append(items):tracks[1].append(new);return True
        timeline=SimpleNamespace(GetTrackCount=lambda kind:len(tracks),GetItemListInTrack=lambda kind,i:tracks[i],AddTrack=add,DeleteTrack=lambda kind,i:tracks.pop(i),SetCurrentTimecode=lambda tc:True)
        pool=SimpleNamespace(ImportMedia=lambda paths:[object()],AppendToTimeline=append)
        with patch.object(workflow,'log'):
            ok,index,items,created,error=workflow.import_srt_to_new_track(timeline,pool,'demo.srt','00:00:00:00')
        self.assertTrue(ok);self.assertEqual(items,[new]);self.assertFalse(created)
        self.assertEqual(tracks,{1:[old,new]})

if __name__=='__main__': unittest.main()
