# Third-party notices

Loc2's original source code uses GPL-3.0-or-later. The components below retain their upstream licenses and notices. [Loc2 license text](LICENSE)

## Coordinate conversion

The Python and Swift coordinate conversion code adapts eviltransform by Googol Lee and contributors. Its original BSD notice is included in the repository and in the app notices. [Original notice](third_party/eviltransform/LICENSE) · [iOS notices](native/loc2-ios/ThirdPartyNotices.txt) · [Upstream project](https://github.com/googollee/eviltransform)

## MacPlay and LIVI

Loc2's WPA3 transition patch modifies MacPlay/LIVI code. The modification and its source baseline are recorded in the November 2, 2026 runtime manifest. The patch follows the upstream GPL-3.0-or-later terms and retains the original authorship. [Patch](tools/runtime-patches/wpa3-transition.patch) · [Runtime manifest](docs/native-runtime-manifest-2026-11-02.json) · [MacPlay](https://github.com/Roylyl/MacPlay) · [LIVI](https://github.com/f-io/LIVI)

## Optional runtime bundles

Bundles prepared with the packaging scripts can contain MacPlay/LIVI, Node.js, GStreamer, Python Build Standalone and GitHub CLI. Follow the license notices and corresponding source requirements of the actual components you bundle. Accessory authentication material and personal provisioning profiles are managed separately. [Packaging guide](docs/releases.md)
