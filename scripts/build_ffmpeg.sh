#!/usr/bin/env bash
# Run in MSYS2 UCRT64 with gcc, make, nasm, curl, tar and xz installed.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/vendor
archive="$PWD/build/vendor/ffmpeg-7.1.1.tar.xz"
curl --fail --location --retry 3 https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz -o "$archive"
echo "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1  $archive" | sha256sum -c -
tar -xf "$archive" -C build
cd build/ffmpeg-7.1.1
# Native FFmpeg components only: no GPL or external codec libraries.
./configure --target-os=mingw32 --arch=x86_64 --disable-autodetect \
  --disable-doc --disable-debug --disable-network --disable-avdevice \
  --disable-ffplay --disable-ffprobe --enable-static --disable-shared \
  --extra-ldflags=-static
make -j2
cp ffmpeg.exe ../vendor/ffmpeg.exe
cp ffbuild/config.log ../vendor/ffmpeg-config.log
cp config.h ../vendor/ffmpeg-config.h
pacman -Q > ../vendor/ffmpeg-toolchain.txt
./ffmpeg.exe -version > ../vendor/ffmpeg-version.txt
