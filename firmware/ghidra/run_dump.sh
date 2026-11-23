#!/usr/bin/env bash
# Re-process the already-analyzed T2F-L310 program with a Java post-script.
# No re-import, no re-analysis (-noanalysis). Needs JDK 25 (same as import).
set -u
GHIDRA="C:/Users/mloco/Downloads/ghidra_12.2_PUBLIC_20261016/ghidra_12.2_PUBLIC"
HERE="c:/Users/mloco/EPS Torque/accord-eps-torque-mod/analysis-2017accord/firmware"
PROJDIR="$HERE/ghidra/project"
PROJNAME="t2f_l310"
SCRIPTDIR="$HERE/ghidra"
PROG="39990-T2F-L310_plain_image.bin"
LOG="$HERE/ghidra/dump.log"

for c in "C:/Program Files/Eclipse Adoptium"/jdk-25*; do
  [ -x "$c/bin/java.exe" ] && export JAVA_HOME="$c" && break
done
echo "JAVA_HOME=$JAVA_HOME"

MSYS_NO_PATHCONV=1 "$GHIDRA/support/analyzeHeadless.bat" \
  "$PROJDIR" "$PROJNAME" \
  -process "$PROG" \
  -noanalysis \
  -scriptPath "$SCRIPTDIR" \
  -postScript DumpSerial.java \
  2>&1 | tee "$LOG"
echo "---- dump complete; log at $LOG ----"
