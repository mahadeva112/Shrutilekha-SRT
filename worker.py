"""Console-subsystem worker; Resolve UI launches it without a console window."""
import runpy
import sys
from app_runtime import prepare_environment, resources

prepare_environment()
if "--self-test" in sys.argv:
    import subprocess
    import transcribe
    assert len(transcribe.languages.LANGUAGES) == 14
    assert (resources() / "data" / "translit_dev.json.gz").is_file()
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    print("Bundled runtime, languages, transcription engine and FFmpeg: OK")
    sys.exit(0)
runpy.run_module("transcribe", run_name="__main__")
