# Loc2

**English** · [简体中文](README.zh-CN.md) · [Download](https://github.com/SAMYJ1/loc2/releases)

Choose a target location on your iPhone and use a Mac to provide that location over USB or a wireless connection. Loc2 is a personal location-testing tool with a native iPhone app and a Mac menu bar app.

- **iPhone:** search Apple Maps, select a point, enter WGS84 coordinates, and manage favorites and recent locations.
- **Mac:** maintain the authorized connection and send location data to the bound iPhone.
- **You:** explicitly apply each target and verify the location actually reported by the phone.

Loc2 requires a Mac and separately supplied accessory authentication files. It is an experimental tool: iOS may reject or filter an external location, and a successful send does not prove that the phone adopted it.

## Features

- Map search, long-press selection, manual coordinates, favorites, and recent targets.
- USB and wireless location delivery, with USB preferred when dual transport is configured.
- QR authorization, TLS connections, and explicit target-device binding.
- Multiple paired Macs, with automatic discovery of an available computer.
- In-app GitHub login to download authentication files from the configured private repository.
- Explicit apply and stop controls. Reconnecting or switching computers never automatically reapplies an old target.

Favorites, recent locations, and the draft stay on the iPhone. The Mac owns the active session and must remain running while it sends location data.

## Requirements

| Component | Requirement |
| --- | --- |
| Mac release | Apple Silicon, macOS 26.0 or later |
| iPhone app | iOS 17.0 or later; Developer Mode for development-signed builds |
| Initial QR pairing | Mac and iPhone on the same local network; a usable private IPv4 address on the Mac |
| Wireless operation | System Bluetooth pairing and Wi-Fi credentials available to Loc2; WPA2 or a supported WPA2/WPA3 mixed network |
| Authentication | Authorized access to `identity.pk8` and `certificate.p7b`, imported separately |

The full Mac release bundles the runtime, Python, and GitHub CLI. It does not include authentication files. GitHub login only downloads them if your account already has access to the private repository; signing in does not grant that access.

Mac releases use a development signature and are not notarized. The supplied IPA is also development-signed: it only installs on devices covered by its provisioning profile and expires with that profile. Check the release notes for signing details. For another iPhone, build and sign the app with your own development team.

## Install

Downloads require repository access while this project is private.

1. Download the Mac ZIP and the appropriate iOS build from [Releases](https://github.com/SAMYJ1/loc2/releases). Check `SHA256SUMS` and `release-metadata.json`.
2. Extract the ZIP, move `Loc2.app` to `/Applications`, and open it.
3. Install the IPA on an eligible iPhone using Xcode or Apple Configurator, or install your own signed build.

The full Mac package automatically prepares its local runtime directory. You do not need to install Python or enter a `runtime` path. Installing or opening the apps does not start location delivery.

The app interface currently uses Chinese. The instructions below include the on-screen labels.

## First-time setup

Complete these steps separately on each Mac.

### 1. Import authentication files

In the Mac menu or details window, choose **From GitHub / 从 GitHub 登录并导入认证材料…**. Sign in with an account that can read `SAMYJ1/loc2-private-auth`. The browser authorization page identifies the application as **GitHub CLI**. After authorization, Loc2 downloads both files from the same repository commit, verifies their SHA-256 checksums, and imports them locally.

If you already have the files, choose **Import runtime authentication / 导入运行时认证材料…** and select this directory instead:

```text
authentication/
├── identity.pk8
└── certificate.p7b
```

Without access to the private repository, you need your own authorized source of these files. Existing, different authentication material is not overwritten. Keep the files out of application source code, public releases, and logs.

### 2. Authorize the iPhone and bind its Bluetooth target

For this wireless setup, disconnect the iPhone's USB cable after installing the app.

1. Keep both devices on the same local network. In the Mac menu, choose **Pair phone controller / 配对手机控制端**.
2. Tap **Scan to connect / 扫码连接** in the iPhone app and scan the QR code. To add another Mac, use **Add computer: scan QR code / 添加电脑：扫描二维码** in the app's settings. Approve the request on the Mac.
3. In the Mac pairing window, select that phone under **Authorized controllers / 已授权控制端**, then click **Bind Bluetooth target / 绑定蓝牙目标…**.
4. Keep the iPhone's **Settings → Bluetooth** page open. Use the Mac's **Search and pair / 搜索并配对附近手机…** button to open system Bluetooth settings and complete pairing. An already paired phone can be selected directly.
5. Return to Loc2, confirm that the selected device is the same iPhone that scanned the code, and click **Confirm binding / 确认绑定**.

QR authorization does not require USB. Bluetooth binding reads the device address automatically and updates the existing authorization; no second scan is needed. This flow configures wireless operation. USB-first operation requires the separate dual-transport configuration described in the [Mac setup guide](docs/mac-app.md).

### 3. Prepare the wireless network

From the Mac menu, run **Initialize or update network authorization / 初始化或更新网络授权…**, then **Check current network / 检查当前网络**. Grant the macOS permissions requested to identify the current Wi-Fi network and access its credentials.

Loc2 selects the local-network interface automatically. Repeat network authorization after changing Wi-Fi credentials or losing Keychain access. WPA3-only networks are not supported by the current runtime; WPA2/WPA3 mixed mode must pass the compatibility check.

### 4. Choose a location

For a first check, use **Enter coordinates / 输入坐标** on the iPhone and enter a known **WGS84** latitude and longitude. Apple Maps search and long-press targets additionally require the coordinate policy described below.

Before applying, check that the Mac is online, the target is available, and the Mac details window shows no missing authentication or network errors.

## Everyday use

1. Keep the Mac app running and open Loc2 on the iPhone.
2. Search, select a map point, enter coordinates, or choose a saved location. This only prepares a draft.
3. Tap **Apply location / 应用位置**. Verify the result on the phone; Mac send counters alone are not confirmation.
4. To finish, tap **Restore / 恢复** on the iPhone or **Stop sending / 停止报点** on the Mac. Observe whether the phone returns to its real location before confirming recovery. If necessary, use the app's location-settings guide to toggle Location Services manually.

Closing the iPhone app does not stop an active Mac session. Quitting or sleeping the Mac, losing the location-delivery connection, or explicitly stopping ends the session. Reconnects and transport changes require a new explicit apply. When switching Macs, resolve any possibly active session on the previous Mac first.

## Enable Apple Maps targets

Manual WGS84 input works without this setting. To apply Apple Maps search or long-press results, the Mac must have a verified native-map coordinate policy. This matters particularly for the distinction between map coordinates in mainland China and the WGS84 location sent to the phone.

After confirming that the validation applies to your app build and region, merge the following into `~/.config/loc2/config.json`, preserving existing settings:

```json
{
  "maps": {
    "native": {
      "coordinatePolicy": "validated-native",
      "validationEvidence": "tests/test_coordinates.py; docs/native-app-validation-2026-10-31.md"
    }
  }
}
```

Restart the Mac app. The iPhone diagnostics should show **Native map calibration / 原生地图校准: 已配置**. Both fields are required. The cited files document this project's coordinate validation; this setting does not perform calibration itself. Revalidate when the provider, coordinate implementation, or region differs, and record the applicable evidence rather than a placeholder.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| QR code missing or Mac unreachable | Same local network, a private IPv4 address, and default port `8767` reachable; avoid copying another Mac's interface name |
| Paired, but no target available | Complete Bluetooth target binding on the Mac; QR authorization alone does not select a location-delivery target |
| GitHub download fails | The signed-in account needs access to the configured private repository; use the account-switch button if necessary |
| Missing authentication or backend startup failure | Import both authentication files and check runtime status in the Mac details window |
| Native map coordinates not calibrated | Configure the verified policy above, or use manual WGS84 coordinates |
| WPA3 compatibility warning | Use a supported WPA2 or WPA2/WPA3 mixed network with the matching runtime, or a configured USB transport |
| Sending stopped, but the phone still shows the target | Verify recovery on the phone; follow the location-settings guide if it does not return to its real location |

## Data and additional Macs

The iPhone stores its places and paired-computer records locally. Mac configuration and authorizations live under `~/.config/loc2`; private runtime data lives under `~/Library/Application Support/loc2`.

Replacing the Mac app normally preserves these directories. For a new Mac, repeat authentication import, QR authorization, target binding, and network setup. Keep each Mac's TLS identity, authorizations, and network settings independent. Coordinate-validation references can be reused only when they still apply.

## Build from source

Use Xcode Command Line Tools and Python 3.9+ for the Mac app and Python tests. iOS builds require full Xcode; device builds also require your Apple development team and signing setup.

```sh
git clone https://github.com/SAMYJ1/loc2.git
cd loc2
python3 -m unittest discover -s tests -v
sh scripts/build-mac-app.sh
open build/Loc2.app
```

```sh
# iOS Simulator build
sh scripts/build-ios-app.sh simulator

# Signed iPhone build: replace YOUR_TEAM_ID with your development team ID
LOC2_TEAM=YOUR_TEAM_ID sh scripts/build-ios-app.sh device
```

A normal source build does not bundle the third-party runtime, Python, or GitHub CLI. Provide a local runtime as described in the [Mac guide](docs/mac-app.md), or follow the [release packaging instructions](docs/releases.md) to create a full distribution. Authentication material is always supplied separately.

## Further reading

Detailed guides are currently in Chinese:

- [Mac configuration, pairing, networks, and USB transport](docs/mac-app.md)
- [Release packaging and signing](docs/releases.md)
- [Pairing and authorization](docs/phone-control.md)
- [Domain terminology](GLOSSARY.md)
