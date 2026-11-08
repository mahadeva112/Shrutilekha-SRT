#!/usr/bin/env bash
# Run on macOS with the Xcode command line tools (clang, make) and curl.
# Builds for the host architecture (arm64 on GitHub's macos-latest runners).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/vendor
archive="$PWD/build/vendor/ffmpeg-7.1.1.tar.xz"
if [ ! -f "$archive" ]; then
  curl --fail --location --retry 3 https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz -o "$archive"
fi
echo "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1  $archive" | shasum -a 256 -c -
tar -xf "$archive" -C build
cd build/ffmpeg-7.1.1
# Native FFmpeg components only: no GPL or external codec libraries, and no
# macOS system frameworks (VideoToolbox etc. stay off via --disable-autodetect).
./configure --disable-autodetect \
  --disable-doc --disable-debug --disable-network --disable-avdevice \
  --disable-ffplay --disable-ffprobe --enable-static --disable-shared
make -j"$(sysctl -n hw.ncpu)"
cp ffmpeg ../vendor/ffmpeg
cp ffbuild/config.log ../vendor/ffmpeg-macos-config.log
cp config.h ../vendor/ffmpeg-macos-config.h
{ sw_vers; uname -m; clang --version; } > ../vendor/ffmpeg-macos-toolchain.txt
./ffmpeg -version > ../vendor/ffmpeg-macos-version.txt
