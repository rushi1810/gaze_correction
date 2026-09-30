@echo off
echo Opening Casablanca
pushd

cd /D "%~dp0"
embeddable-python\python application\main.py

popd