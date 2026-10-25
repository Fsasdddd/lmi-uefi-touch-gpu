#!/bin/bash
# Clang's cctools-compatible command omits the modern platform tuple that
# ld64.lld requires. All desktop userland artifacts target the existing iOS16.5.
exec /usr/lib/llvm-18/bin/ld64.lld -platform_version ios 16.5 16.5 "$@"
