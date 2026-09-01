#!/usr/bin/env bash
# Headless Hong Kong 97 SMS boot/flow verification in MesenCE.
# renders / capture a screenshot. Linux counterpart of tools/smoke.ps1.
#
#   ./tools/smoke.sh --rom build/hong-kong-97-sms.sms
#   ./tools/smoke.sh --rom build/hong-kong-97-sms.sms --flow --frames 900
#
# MESEN_BIN overrides the emulator path (default: MesenCE source build —
# the stock AOT Mesen 2.1.1 crashes on Ubuntu 26.04, see
# conversion-desk/knowledge/topics/emulators.md).

set -euo pipefail

ROM="" ; SHOT="docs/screenshots/m0-boot.png" ; FRAMES=150 ; MODE="boot"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rom)  ROM="$2"; shift 2 ;;
    --shot) SHOT="$2"; shift 2 ;;
    --frames) FRAMES="$2"; shift 2 ;;
    --flow) MODE="flow"; shift ;;
    --capture) shift ;;  # accepted for smoke.ps1 parity; screenshot always kept
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$ROM" && -f "$ROM" ]] || { echo "ROM not found: $ROM" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ "$ROM"  = /* ]] || ROM="$(pwd)/$ROM"
[[ "$SHOT" = /* ]] || SHOT="$(pwd)/$SHOT"
mkdir -p "$(dirname "$SHOT")"
rm -f "$SHOT"

MESEN_BIN="${MESEN_BIN:-$HOME/tools/mesen-src/bin/linux-x64/Release/Mesen}"
MESEN_HOME_NAME="${MESEN_HOME_NAME:-MesenCE}"
[[ -x "$MESEN_BIN" ]] || { echo "Mesen not found: $MESEN_BIN (set MESEN_BIN)" >&2; exit 2; }

WORK=$(mktemp -d "${TMPDIR:-/tmp}/hk97-sms-smoke.XXXXXX")
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT HUP INT TERM

# Isolated Mesen home: testrunner needs native libs + a settings.json (a
# missing settings.json opens the first-run wizard instead of the testrunner).
CFG="$WORK/home/.config/$MESEN_HOME_NAME"
mkdir -p "$CFG"
for lib in MesenCore.so libSkiaSharp.so libHarfBuzzSharp.so; do
  for src in "$HOME/.config/$MESEN_HOME_NAME/$lib" "$(dirname "$MESEN_BIN")/$lib"; do
    if [[ ! -f "$CFG/$lib" && -f "$src" ]]; then cp "$src" "$CFG/$lib"; fi
  done
done
# NtscOverscan 8/8: Mesen's SMS canvas is 240 lines and the default 24/24
# crop would hide the top/bottom 16 lines of this ROM's 224-line mode.
# Port1 Type 45 = ControllerType::SmsController - headless defaults to None
# (no pad!), which silently eats emu.setInput.  Lua buttons: "one"/"two".
cat > "$CFG/settings.json" <<'EOF'
{
  "Debug": { "ScriptWindow": { "AllowIoOsAccess": true } },
  "Sms": {
    "RamPowerOnState": 1,
    "Port1": { "Type": 45 },
    "NtscOverscan": { "Top": 8, "Bottom": 8, "Left": 0, "Right": 0 }
  }
}
EOF

export HOME="$WORK/home"
unset XDG_CONFIG_HOME
export DOTNET_ROLL_FORWARD="${DOTNET_ROLL_FORWARD:-LatestMajor}"
export SHOT FRAMES MODE

echo "[smoke] emu : $MESEN_BIN"
echo "[smoke] rom : $ROM (mode=$MODE frames=$FRAMES)"
set +e
xvfb-run -a "$MESEN_BIN" \
  --testrunner \
  --timeout=90 \
  --debug.scriptwindow.allowioosaccess=true \
  "$ROM" \
  "${SMOKE_LUA:-$REPO_ROOT/tools/lua/mesen_smoke.lua}" \
  >"$WORK/mesen.log" 2>&1
STATUS=$?
set -e

if [[ -n "${SMOKE_LOG:-}" ]]; then cat "$WORK/mesen.log"; fi
if [[ -f "$SHOT" && -s "$SHOT" ]]; then
  echo "[smoke] PASS - ROM booted and rendered a frame: $SHOT"
  exit 0
fi
echo "[smoke] FAIL - no frame captured (mesen exit $STATUS). log:" >&2
cat "$WORK/mesen.log" >&2 || true
exit 1
