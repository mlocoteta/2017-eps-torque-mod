#!/usr/bin/env bash
# Headless Ghidra import + auto-analysis + serial dump for the T2F-L310 image.
# Run from git-bash after installing JDK 25. Optional arg $1 = JAVA_HOME override.
set -u

GHIDRA="C:/Users/mloco/Downloads/ghidra_12.2_PUBLIC_20261016/ghidra_12.2_PUBLIC"
HERE="c:/Users/mloco/EPS Torque/accord-eps-torque-mod/analysis-2017accord/firmware"
IMAGE="$HERE/39990-T2F-L310_plain_image.bin"
PROJDIR="$HERE/ghidra/project"
PROJNAME="t2f_l310"
SCRIPTDIR="$HERE/ghidra"
LOG="$HERE/ghidra/headless.log"

# --- locate JDK 25 (Ghidra 12.2 requires application.java.min=25) ---
if [ $# -ge 1 ]; then
  export JAVA_HOME="$1"
else
  for c in "C:/Program Files/Eclipse Adoptium"/jdk-25* \
           "C:/Program Files/Java"/jdk-25* \
           "C:/Program Files/Microsoft"/jdk-25* \
           "C:/Users/mloco/.jdks"/*25*; do
    [ -x "$c/bin/java.exe" ] && export JAVA_HOME="$c" && break
  done
fi
if [ -z "${JAVA_HOME:-}" ] || [ ! -x "$JAVA_HOME/bin/java.exe" ]; then
  echo "JDK 25 not found. Install Temurin JDK 25, or pass JAVA_HOME as arg 1."
  exit 2
fi
echo "JAVA_HOME = $JAVA_HOME"
"$JAVA_HOME/bin/java.exe" -version

mkdir -p "$PROJDIR"
# Import flat V850 binary at base 0x0, auto-analyze, run the serial dump post-script.
MSYS_NO_PATHCONV=1 "$GHIDRA/support/analyzeHeadless.bat" \
  "$PROJDIR" "$PROJNAME" \
  -import "$IMAGE" \
  -processor "V850:LE:32:default" \
  -loader BinaryLoader \
  -loader-baseAddr 0x0 \
  -scriptPath "$SCRIPTDIR" \
  -postScript dump_serial.py \
  2>&1 | tee "$LOG"

echo "---- headless run complete; log at $LOG ----"
