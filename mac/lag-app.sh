#!/bin/bash
# Lager Golflager.app i Programmer-mappen din og legger den i Dock (første gang),
# så du kan starte Golflager med ett klikk. Kjøres automatisk av start.sh.
APP_DIR="$(cd "${1:-$(dirname "$0")/..}" && pwd)"
TARGET="${GOLFLAGER_APP_TARGET:-$HOME/Applications/Golflager.app}"
NEW=0
[ -d "$TARGET" ] || NEW=1

mkdir -p "$TARGET/Contents/MacOS" "$TARGET/Contents/Resources" || exit 1
cp "$APP_DIR/mac/Info.plist" "$TARGET/Contents/Info.plist"
cp "$APP_DIR/mac/Golflager" "$TARGET/Contents/MacOS/Golflager"
chmod +x "$TARGET/Contents/MacOS/Golflager"
cp "$APP_DIR/mac/Golflager.icns" "$TARGET/Contents/Resources/Golflager.icns"
printf '%s' "$APP_DIR" > "$TARGET/Contents/Resources/mappe.txt"
touch "$TARGET"  # får Finder til å vise det nye ikonet

if [ "$(uname)" = "Darwin" ]; then
  # Filene kommer fra en nedlastet ZIP og er merket med «karantene». Programmet lages her
  # på Macen, så vi fjerner merket, ellers kan Macen nekte å åpne det.
  xattr -cr "$TARGET" >/dev/null 2>&1
  # Gjør programmet kjent for Spotlight og Launchpad med én gang
  LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  [ -x "$LSREGISTER" ] && "$LSREGISTER" -f "$TARGET" >/dev/null 2>&1
  # Legg ikonet i Dock første gang (bare hvis det ikke ligger der fra før)
  if [ "$NEW" = 1 ] && ! defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "Golflager.app"; then
    defaults write com.apple.dock persistent-apps -array-add \
      "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$TARGET</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>" \
      && killall Dock >/dev/null 2>&1
    echo "  ⛳  Golflager ligger nå i Dock. Neste gang klikker du bare på ikonet."
  fi
fi
exit 0
