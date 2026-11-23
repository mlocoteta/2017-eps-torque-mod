#!/usr/bin/env bash
set -u
GHIDRA="C:/Users/mloco/Downloads/ghidra_12.2_PUBLIC_20261016/ghidra_12.2_PUBLIC"
HERE="c:/Users/mloco/EPS Torque/accord-eps-torque-mod/analysis-2017accord/firmware"
for c in "C:/Program Files/Eclipse Adoptium"/jdk-25*; do [ -x "$c/bin/java.exe" ] && export JAVA_HOME="$c" && break; done
MSYS_NO_PATHCONV=1 "$GHIDRA/support/analyzeHeadless.bat" "$HERE/ghidra/project" t2f_l310 \
  -process "39990-T2F-L310_plain_image.bin" -noanalysis \
  -scriptPath "$HERE/ghidra" -postScript DumpFuncs.java "$@"
