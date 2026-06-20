# syntax=docker/dockerfile:1
# Builds libtdjson.so from a pinned TDLib release — the native library the opt-in Telegram TDLib
# path binds via ctypes (NativeTdjsonClient). It is a full C++ build (heavy + slow), so it lives in
# its own image used only when TDLib is enabled: the compose `tdlib-lib` init service runs this and
# copies the resulting shared library into a volume the gateway + TDLib worker mount read-only. That
# keeps the app images lean and delivers libtdjson as a mounted artifact — no app-image rebuild.
#
# Built on the same Debian (bookworm) base as the app images (python:3.12-slim) so the .so's
# OpenSSL/zlib ABI matches the runtime that loads it. Bump TDLIB_REF to move TDLib versions.
FROM python:3.12-slim AS build

ARG TDLIB_REF=v1.8.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        git cmake g++ make zlib1g-dev libssl-dev gperf ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone https://github.com/tdlib/td.git \
    && cd td \
    && git checkout "${TDLIB_REF}" \
    && mkdir build && cd build \
    && cmake -DCMAKE_BUILD_TYPE=Release .. \
    && cmake --build . --target tdjson -j"$(nproc)" \
    && mkdir -p /opt/td/lib \
    && find . -name 'libtdjson.so*' -exec cp -a {} /opt/td/lib/ \;

# The shared library now lives at /opt/td/lib/libtdjson.so* — the `tdlib-lib` compose service copies
# it into the shared volume. A no-op default command; compose overrides it with the copy.
CMD ["sh", "-c", "ls -l /opt/td/lib"]
