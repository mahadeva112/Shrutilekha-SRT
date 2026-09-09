@echo off
setlocal EnableDelayedExpansion
title Srutilekha - Setup

:: Always run from this script's own folder
cd /d "%~dp0"

cls
echo ============================================================
echo    Srutilekha  --  Setup  (Windows)
echo ============================================================
echo.

:: ── 1. Python check ───────────────────────────────────────────
echo [ 1 / 5 ]  Checking Python...
set "PYEXE="

:: Prefer the official Windows py launcher — it bypasses the Microsoft Store
:: app-execution-alias stub that lives in %LOCALAPPDATA%\Microsoft\WindowsApps.
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=py -3"
) else (
    :: Fall back to scanning `where python` and skipping the WindowsApps stub.
    for /f "delims=" %%p in ('where python 2^>nul') do (
        if not defined PYEXE (
            echo %%p | findstr /I "WindowsApps" >nul
            if errorlevel 1 set "PYEXE=%%p"
        )
    )
)

if not defined PYEXE (
    echo.
    echo   ERROR: No working Python found on PATH.
    echo   ^(Microsoft Store stub at %%LOCALAPPDATA%%\Microsoft\WindowsApps does not count.^)
    echo.
    echo   Download from:  https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: During install, check the box:
    echo   "Add Python to PATH"
    echo.
    echo   After installing, also disable the Store alias:
    echo   Settings ^> Apps ^> Advanced app settings ^> App execution aliases
    echo   and turn OFF the "python.exe" and "python3.exe" entries.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('%PYEXE% --version 2^>^&1') do echo   OK -- %%v ^(%PYEXE%^)

:: ── 2. Python packages ────────────────────────────────────────
::
:: --user keeps everything inside %APPDATA%\Python, so this works even when
:: Python was installed for all users into Program Files (where the global
:: site-packages needs admin to write).
::
:: truststore makes Python verify TLS against the Windows certificate store
:: instead of certifi's bundle. On a network that inspects HTTPS (corporate
:: proxy, some antivirus) that is the difference between the ElevenLabs call
:: working and dying with CERTIFICATE_VERIFY_FAILED.
echo.
echo [ 2 / 5 ]  Installing Python packages...
%PYEXE% -m pip install --quiet --user elevenlabs
if not errorlevel 1 goto core_ok

:: Chicken and egg: on an intercepted network pip cannot download the very
:: package that fixes intercepted networks, because pip's own HTTPS fails the
:: same way. Export the Windows root store to a PEM and hand it to pip
:: directly. Reading the cert stores is unprivileged - no admin needed.
echo   First attempt failed. Trying again with Windows certificates...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$out=@(); foreach($p in 'Cert:\LocalMachine\Root','Cert:\LocalMachine\CA','Cert:\CurrentUser\Root','Cert:\CurrentUser\CA'){ Get-ChildItem $p -ErrorAction SilentlyContinue | ForEach-Object { $out += '-----BEGIN CERTIFICATE-----'; $out += [Convert]::ToBase64String($_.RawData,'InsertLineBreaks'); $out += '-----END CERTIFICATE-----' } }; Set-Content -Path 'certs.pem' -Value $out -Encoding ascii" >nul 2>&1

if not exist certs.pem (
    echo.
    echo   ERROR: pip install failed and the certificate export did not run.
    echo   Check your internet connection and try again.
    pause
    exit /b 1
)

%PYEXE% -m pip install --quiet --user --cert "%CD%\certs.pem" elevenlabs
if not errorlevel 1 goto core_ok_cert

:: --user is itself refused inside a virtualenv, which has nothing to do with
:: certificates. One last plain attempt so that case doesn't get reported as an
:: SSL problem.
%PYEXE% -m pip install --quiet --cert "%CD%\certs.pem" elevenlabs
if not errorlevel 1 goto core_ok_cert

echo.
echo   ERROR: pip install still failed.
echo.
echo   If the error mentions CERTIFICATE_VERIFY_FAILED or SSL, this
echo   network is inspecting HTTPS traffic. Ask IT for the proxy's
echo   root CA file ^(.cer/.pem^) and run:
echo.
echo     set SSL_CERT_FILE=C:\path\to\that\file.pem
echo     %PYEXE% -m pip install --user elevenlabs
echo.
echo   Otherwise, check your internet connection.
pause
exit /b 1

:core_ok_cert
echo   OK -- elevenlabs ^(via the Windows certificate store^)
goto truststore_step

:core_ok
echo   OK -- elevenlabs

:truststore_step
:: truststore is deliberately a SEPARATE, non-fatal install. It needs Python
:: 3.10+, and bundling it with elevenlabs would mean an older Python fails the
:: whole command and takes the required package down with it. It only matters
:: on a network that inspects HTTPS, so a machine without it is still fine.
if exist certs.pem (
    %PYEXE% -m pip install --quiet --user --cert "%CD%\certs.pem" truststore
) else (
    %PYEXE% -m pip install --quiet --user truststore
)
if errorlevel 1 (
    echo   NOTE: truststore was not installed ^(it needs Python 3.10+^).
    echo   Harmless on a normal network. If transcription later fails with a
    echo   certificate error, this is the piece that would have prevented it.
) else (
    echo   OK -- truststore
)

:: ── 3. tkinter (bundled with Python on Windows — just verify) ─
echo.
echo [ 3 / 5 ]  Checking tkinter...
%PYEXE% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo   WARNING: tkinter not found.
    echo   Re-install Python and make sure "tcl/tk" option is checked.
) else (
    echo   OK
)

:: ── 4. Save project path for the Resolve script ───────────────
echo.
echo [ 4 / 5 ]  Saving project path...
echo %CD%> "%USERPROFILE%\.audio_to_srt_path"
echo   OK -- path saved to %%USERPROFILE%%\.audio_to_srt_path

:: ── 5. Install the script into Resolve ────────────────────────
echo.
echo [ 5 / 5 ]  Installing Srutilekha.py into DaVinci Resolve...
::
:: Python, not Lua. Resolve 21.1 runs menu scripts on built-in interpreters and
:: sandboxes the Lua one without the `io` table, so audio_to_srt.lua dies on its
:: first file read and the menu entry appears to do nothing at all. See the
:: header comment in audio_to_srt.py. The .lua is kept in the repo for Resolve
:: 21.0 and earlier but is no longer installed -- two files here would also mean
:: two identical "Srutilekha" entries in the same menu.
::
:: Resolve scans two Utility folders. The %ProgramData% one is machine-wide and
:: needs admin to write; the %APPDATA% one is per-user and does not. Both show
:: up under the same Workspace > Scripts menu, so install to the per-user path
:: and never ask for elevation.
set "RESOLVE_USER=%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"
set "RESOLVE_SYS=%ProgramData%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility"

if not exist "%RESOLVE_USER%" mkdir "%RESOLVE_USER%" >nul 2>&1
copy /Y audio_to_srt.py "%RESOLVE_USER%\Srutilekha.py" >nul 2>&1

:: Check the file, not the exit code. `copy` reports success in cases where
:: nothing was written (a locked destination, a full disk), and a setup that
:: says OK while the menu stays empty is the worst outcome here.
if not exist "%RESOLVE_USER%\Srutilekha.py" goto install_failed
echo   OK -- installed to %%APPDATA%%\...\Fusion\Scripts\Utility
echo        Open it from:  Workspace ^> Scripts ^> Srutilekha

:: The Lua entry a previous setup left behind: same menu name, and on Resolve
:: 21.1 it only ever errors. Remove it so there is one Srutilekha and it works.
if not exist "%RESOLVE_USER%\Srutilekha.lua" goto sys_lua
del /F /Q "%RESOLVE_USER%\Srutilekha.lua" >nul 2>&1
:: `del` prints "Access is denied" and still leaves errorlevel 0, so the only
:: honest test is whether the file is gone.
if exist "%RESOLVE_USER%\Srutilekha.lua" (
    echo.
    echo   NOTE: the old Lua entry could not be removed:
    echo   %RESOLVE_USER%\Srutilekha.lua
    echo   Resolve will list a second "Srutilekha" that does not work.
    echo   Close Resolve and delete that file.
) else (
    echo   OK -- removed the old Lua entry ^(it cannot run on Resolve 21.1^)
)

:sys_lua
:: A leftover copy in ProgramData from an older admin install would show a
:: second, stale "Srutilekha" in the same menu. Clear it if we can, warn if we
:: cannot -- we are deliberately not elevating.
if not exist "%RESOLVE_SYS%\Srutilekha.lua" goto sys_py
del /F /Q "%RESOLVE_SYS%\Srutilekha.lua" >nul 2>&1
if exist "%RESOLVE_SYS%\Srutilekha.lua" (
    echo.
    echo   NOTE: a stale Lua copy exists at:
    echo   %RESOLVE_SYS%\Srutilekha.lua
    echo   It could not be removed without admin rights, and Resolve will list
    echo   it as a second "Srutilekha" entry that does not work. Delete that
    echo   file when convenient.
)

:sys_py
:: Only refresh a machine-wide copy that is already there. Creating one would
:: need admin, and the per-user install above already reaches the same menu.
if not exist "%RESOLVE_SYS%\Srutilekha.py" goto install_done
copy /Y audio_to_srt.py "%RESOLVE_SYS%\Srutilekha.py" >nul 2>&1
fc /B audio_to_srt.py "%RESOLVE_SYS%\Srutilekha.py" >nul 2>&1
if not errorlevel 1 goto install_done
echo.
echo   NOTE: an older copy exists at:
echo   %RESOLVE_SYS%\Srutilekha.py
echo   It could not be updated without admin rights, and Resolve will list it
echo   as a duplicate menu entry running an older version. Delete that file
echo   when convenient.
goto install_done

:install_failed
echo   WARNING: could not write to:
echo   %RESOLVE_USER%
echo   Please copy audio_to_srt.py there manually as Srutilekha.py.
echo   ^(If Resolve is running, close it and run setup.bat again.^)

:install_done

:: ── API key ────────────────────────────────────────────────────
echo.
echo ------------------------------------------------------------
if exist .env (
    findstr /C:"ELEVENLABS_API_KEY=" .env >nul 2>&1
    if not errorlevel 1 (
        echo   API key already saved in .env  --  skipping.
        goto done
    )
)
echo   ElevenLabs API key setup
echo   Get your key at: https://elevenlabs.io/app/speech-synthesis/api
echo.
set /p APIKEY="  Paste your API key and press Enter: "
if not "!APIKEY!"=="" (
    echo ELEVENLABS_API_KEY=!APIKEY!> .env
    echo   OK -- saved to .env
) else (
    echo   Skipped. Add it later by editing .env in this folder.
)

:done
echo.
echo ============================================================
:: ^! and not ! — delayed expansion is on for this whole file, and it eats a
:: bare exclamation mark, so the banner has always read "Setup complete".
echo    Setup complete^!
echo ============================================================
echo.
echo    Open DaVinci Resolve
echo    Go to:  Workspace  -^>  Scripts  -^>  Srutilekha
echo.
pause
