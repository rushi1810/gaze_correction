setlocal
cd /d %~dp0
:: Uninstall old version if any
devcon.exe /r remove "ROOT\CasablancaCamera"

:: Now install the new one
devcon.exe install CasablancaCamera.inf ROOT\CasablancaCamera
