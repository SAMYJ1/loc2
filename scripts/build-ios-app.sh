#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 "$project_root/scripts/prepare-location-settings-shortcut.py"
python3 "$project_root/scripts/generate-ios-project.py"
mode=${1:-simulator}
case "$mode" in
simulator)
    xcodebuild -project "$project_root/native/loc2-ios/loc2.xcodeproj" -scheme loc2 -sdk iphonesimulator -configuration Debug -derivedDataPath "$project_root/build/ios-simulator" CODE_SIGNING_ALLOWED=NO build
    ;;
device|release)
    : "${LOC2_TEAM:?Set LOC2_TEAM to your local Xcode development team}"
    configuration=Debug
    [ "$mode" != release ] || configuration=Release
    xcodebuild -project "$project_root/native/loc2-ios/loc2.xcodeproj" -scheme loc2 -sdk iphoneos -configuration "$configuration" -destination 'generic/platform=iOS' -derivedDataPath "$project_root/build/ios-device" -allowProvisioningUpdates "DEVELOPMENT_TEAM=$LOC2_TEAM" "MARKETING_VERSION=${LOC2_VERSION:-1.0}" "CURRENT_PROJECT_VERSION=${LOC2_BUILD:-1}" build
    ;;
*) printf '%s\n' 'Usage: build-ios-app.sh simulator|device|release' >&2;exit 2 ;;
esac
