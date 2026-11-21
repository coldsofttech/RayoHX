; NSIS installer for the desktop app (rayohxu, with rayohx beside it). Windows only; see
; installer\windows\nsis\common.nsh for the options.
;
;   makensis /DAPP_NAME="RayoHX" /DAPP_VERSION=0.1.0 /DSOURCE_DIR=..\..\build\installer\rayohxu \
;            /DOUT_FILE=..\..\dist\rayohxu-0.1.0-setup.exe packages\ui\installer\windows\ui.nsi
; packages/ui/scripts/build_installer.py does this from the project's own metadata.

; Stable id of this product: keep it for the life of the project, so a newer setup replaces an
; older install. Generate a new one for your project (python -c "import uuid; print(uuid.uuid4())").
!define GUID "{13C161C2-BD1D-4ACB-A31C-F9D1BC7B3DDA}"
!define MAIN_EXE "rayohxu.exe"
!define EXTRA_EXE "rayohx.exe"
!define HAS_DESKTOP

; common.nsh is shared with the command line's installer, so it stays in the root installer/ folder.
!addincludedir "${__FILEDIR__}\..\..\..\..\installer\windows\nsis"
!include "common.nsh"
