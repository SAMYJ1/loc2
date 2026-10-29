#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app="$project_root/build/Location Lab.app"
deployment_target=13.0
target_arch=$(uname -m)
case "$target_arch" in arm64|x86_64) ;; *) printf '%s\n' "Unsupported macOS architecture: $target_arch" >&2; exit 1 ;; esac
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
xcrun swiftc -O -target "$target_arch-apple-macosx$deployment_target" -framework AppKit "$project_root/native/LocationLab/main.swift" -o "$app/Contents/MacOS/LocationLab"
# This generated package must reflect deletions/renames in the source as well as additions.
rm -rf "$app/Contents/Resources/location_lab"
cp -R "$project_root/location_lab" "$app/Contents/Resources/"
find "$app/Contents/Resources/location_lab" -name __pycache__ -type d -prune -exec rm -rf {} +
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.location-lab.app</string>
<key>CFBundleName</key><string>Location Lab</string>
<key>CFBundleExecutable</key><string>LocationLab</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSUIElement</key><true/>
<key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
PLIST
binary_minimum=$(xcrun vtool -show-build "$app/Contents/MacOS/LocationLab" | awk '$1 == "minos" { print $2 }')
bundle_minimum=$(/usr/bin/plutil -extract LSMinimumSystemVersion raw -o - "$app/Contents/Info.plist")
if [ "$binary_minimum" != "$deployment_target" ] || [ "$bundle_minimum" != "$deployment_target" ]; then
    printf '%s\n' "Deployment target mismatch: binary=$binary_minimum bundle=$bundle_minimum expected=$deployment_target" >&2
    exit 1
fi
codesign --force --sign - "$app"
printf '%s\n' "$app"
