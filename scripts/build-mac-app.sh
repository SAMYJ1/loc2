#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app="$project_root/build/Loc2.app"
# Preserve the installed app's signing identity so its keychain entries remain trusted.
signing_identity=${LOC2_MAC_SIGN_IDENTITY:-}
if [ -z "$signing_identity" ]; then
    signing_identity=$(python3 - "$app" <<'PY'
import pathlib,subprocess,sys
app=next((pathlib.Path(value) for value in sys.argv[1:] if pathlib.Path(value).exists()),pathlib.Path(sys.argv[1]))
details=subprocess.run(['codesign','-dvv',str(app)],capture_output=True,text=True).stderr if app.exists() else ''
authority=next((line.split('=',1)[1] for line in details.splitlines() if line.startswith('Authority=')),None)
if authority:
    identities=subprocess.check_output(['security','find-identity','-v','-p','codesigning'],text=True)
    identity=next((line.split()[1] for line in identities.splitlines() if '"'+authority+'"' in line),None)
    if not identity:
        sys.exit('Existing app signing identity is unavailable; restore it or explicitly set LOC2_MAC_SIGN_IDENTITY.')
    print(identity)
else:
    print('-')
PY
)
fi
deployment_target=13.0
target_arch=$(uname -m)
sdk_path=$(xcrun --sdk macosx --show-sdk-path)
case "$target_arch" in arm64|x86_64) ;; *) printf '%s\n' "Unsupported macOS architecture: $target_arch" >&2; exit 1 ;; esac
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
xcrun swiftc -sdk "$sdk_path" -O -target "$target_arch-apple-macosx$deployment_target" -framework AppKit -framework ServiceManagement -framework CoreWLAN -framework CoreLocation -framework Security "$project_root/native/loc2-mac/"*.swift -o "$app/Contents/MacOS/loc2"
# This generated package must reflect deletions/renames in the source as well as additions.
rm -rf "$app/Contents/Resources/loc2"
cp -R "$project_root/loc2" "$app/Contents/Resources/"
cp "$project_root/third_party/eviltransform/LICENSE" "$app/Contents/Resources/ThirdPartyNotices.txt"
find "$app/Contents/Resources/loc2" -name __pycache__ -type d -prune -exec rm -rf {} +
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.loc2.app</string>
<key>CFBundleName</key><string>Loc2</string>
<key>CFBundleDisplayName</key><string>Loc2</string>
<key>CFBundleExecutable</key><string>loc2</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSUIElement</key><true/>
<key>NSLocationUsageDescription</key><string>macOS 要求定位权限才能识别当前 Wi-Fi 名称和接入点。本应用不读取或保存 Mac 的定位坐标。</string>
<key>NSLocationWhenInUseUsageDescription</key><string>识别当前 Wi-Fi 网络，用于无线连接已授权的 iPhone；不采集 Mac 的位置轨迹。</string>
<key>NSBluetoothAlwaysUsageDescription</key><string>与已授权 iPhone 建立无线配件连接，提供你明确应用的目标位置。</string>
<key>NSBluetoothPeripheralUsageDescription</key><string>与已授权 iPhone 建立无线配件连接。</string>
<key>NSLocalNetworkUsageDescription</key><string>让手机 App 通过同一网络连接本机后台服务。</string>
<key>NSBonjourServices</key><array><string>_loc2._tcp.</string></array>
<key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
PLIST
binary_minimum=$(xcrun vtool -show-build "$app/Contents/MacOS/loc2" | awk '$1 == "minos" { print $2 }')
bundle_minimum=$(/usr/bin/plutil -extract LSMinimumSystemVersion raw -o - "$app/Contents/Info.plist")
if [ "$binary_minimum" != "$deployment_target" ] || [ "$bundle_minimum" != "$deployment_target" ]; then
    printf '%s\n' "Deployment target mismatch: binary=$binary_minimum bundle=$bundle_minimum expected=$deployment_target" >&2
    exit 1
fi
codesign --force --sign "$signing_identity" --timestamp=none "$app"
printf '%s\n' "$app"
