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
    def test_apply_api_failure_reports_to_window_and_restores_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_client=SimpleNamespace(connect=lambda:({},object()),rejected_style_properties=0)
            def failing_main():
                run=workflow.Run()
                run.launch_loader()
                raise BridgeError('AppendToTimeline unavailable')
            with patch('resolve_bridge.BridgeClient',return_value=fake_client), \
                 patch.object(workflow,'LOGS_DIR',tmp),patch.object(workflow,'log'), \
                 patch.object(workflow,'main',side_effect=failing_main), \
                 patch.object(workflow.Run,'launch_loader',return_value=True) as launch, \
                 patch.object(workflow.Run,'report') as report,patch.object(workflow.Run,'cleanup') as cleanup:
                from resolve_bridge import _run_workflow
                _run_workflow()
                self.assertTrue(report.call_args.args[1].startswith('ERROR\n'))
                self.assertIn('AppendToTimeline unavailable',report.call_args.args[1])
                cleanup.assert_called_once()
                self.assertIs(workflow.Run.launch_loader,launch)

    def test_resolve_21_flagged_collections_map_real_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=BridgeClient(tmp,Path(tmp)/'prefs')
            media=SimpleNamespace(GetClipProperty=lambda:{'File Path':'demo.wav'})
            clip=SimpleNamespace(GetMediaPoolItem=lambda:media,GetLeftOffset=lambda:0,
                                 GetStart=lambda:24,GetEnd=lambda:48,GetPlayBackSpeed=lambda:1)
            with patch.object(client,'request',return_value={'1':clip,'__flags':0}):
                clips=client.call(1,'GetItemListInTrack',['audio',2])
            count,path=workflow.collect_clip_ranges(SimpleNamespace(ranges=str(Path(tmp)/'ranges')),
                                                    None,clips,24,0)
            self.assertEqual((count,path),(1,'demo.wav'))
            with patch.object(client,'request',return_value={'__flags':0}):
                self.assertEqual(client.call(1,'GetClipList',[]),[])
            with patch.object(client,'request',return_value={'File Path':'demo.wav','__flags':0}):
                self.assertEqual(client.call(1,'GetClipProperty',[])['File Path'],'demo.wav')

    def test_media_api_failure_is_reported_instead_of_silently_skipping_audio(self):
        clip=SimpleNamespace(GetMediaPoolItem=lambda:(_ for _ in ()).throw(BridgeError('API unavailable')))
        with patch.object(workflow,'log'):
            with self.assertRaisesRegex(RuntimeError,'API unavailable'):
                workflow.collect_clip_ranges(None,None,[clip],24,0)

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
        def append(items):
            self.assertEqual(set(items[0]),{'mediaPoolItem'})
            tracks[1].append(new);return True
        timeline=SimpleNamespace(GetTrackCount=lambda kind:len(tracks),GetItemListInTrack=lambda kind,i:tracks[i],AddTrack=add,DeleteTrack=lambda kind,i:tracks.pop(i),SetCurrentTimecode=lambda tc:True)
        pool=SimpleNamespace(ImportMedia=lambda paths:[object()],AppendToTimeline=append)
        with patch.object(workflow,'log'):
            ok,index,items,created,error=workflow.import_srt_to_new_track(timeline,pool,'demo.srt','00:00:00:00')
        self.assertTrue(ok);self.assertEqual(items,[new]);self.assertFalse(created)
        self.assertEqual(tracks,{1:[old,new]})

if __name__=='__main__': unittest.main()
