#!/bin/zsh
export PATH="./Resources/python/bin/Casablanca:$PATH"
export IMAGEIO_FFMPEG_EXE="/Library/Application Support/Casablanca/app-ort/Resources/python/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"
./Resources/python/bin/Casablanca application/main.py --is_started_from_app 2>&1 | tee -a persistent/logs_with_stdout.log