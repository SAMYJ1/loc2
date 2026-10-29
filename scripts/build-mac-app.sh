#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app="$project_root/build/Location Lab.app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
xcrun swiftc -O -framework AppKit "$project_root/native/LocationLab/main.swift" -o "$app/Contents/MacOS/LocationLab"
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
codesign --force --sign - "$app"
printf '%s\n' "$app"
