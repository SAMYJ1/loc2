# Loc2

**English** · [简体中文](README.zh-CN.md) · [GPL-3.0-or-later](LICENSE)

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
| Mac runtime | Apple Silicon and macOS 26.0 or later for the documented runtime |
| iPhone app | iOS 17.0 or later; Developer Mode for development-signed builds |
| Initial QR pairing | Mac and iPhone on the same local network; a usable private IPv4 address on the Mac |
| Wireless operation | System Bluetooth pairing and Wi-Fi credentials available to Loc2; WPA2 or a supported WPA2/WPA3 mixed network |
| Authentication | Authorized access to `identity.pk8` and `certificate.p7b`, imported separately |

## Install

1. Build both apps from the public source. Use your own Apple development team to sign and install the iPhone app. [Build from source](#build-from-source)
2. Prepare a compatible location runtime in a local directory and set its path in the Mac configuration. [Mac runtime setup](docs/mac-app.md#本机运行时配置)
3. Open Loc2 on both devices and import your authorized accessory authentication files in the Mac app.

The app interface currently uses Chinese. The instructions below include the on-screen labels.

## First-time setup

Complete these steps separately on each Mac.

### 1. Import authentication files

In the Mac menu, choose **Import runtime authentication / 导入运行时认证材料…** and select a directory containing the two files you are authorized to use.

```text
authentication/
├── identity.pk8
└── certificate.p7b
```

Accounts with access to the private credential repository can also use **From GitHub / 从 GitHub 登录并导入认证材料…**. The browser authorization page shows **GitHub CLI**. Loc2 downloads both files from one repository commit and checks their SHA-256 digests before importing them locally. Keep the files in your private runtime directory. [Authentication setup](docs/mac-app.md#从-github-一键导入认证材料)

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

Install the signed device build from `build/ios-device/Build/Products/Debug-iphoneos/Loc2.app` using Xcode's Devices and Simulators window. If your team needs a different bundle identifier, open `native/loc2-ios/loc2.xcodeproj`, set the identifier and signing team, then build and run from Xcode.

Source builds use a locally supplied runtime and Python. The packaging guide covers assembling a complete bundle with compatible third-party components. [Mac setup](docs/mac-app.md) · [Packaging](docs/releases.md)

## License

Loc2's original source code is copyright © 2026 Loc2 contributors and is licensed under **GPL-3.0-or-later**. [License text](LICENSE)

Third-party components retain their original licenses and attribution. [Third-party notices](THIRD_PARTY_NOTICES.md)

## Further reading

Detailed guides are currently in Chinese:

- [Mac configuration, pairing, networks, and USB transport](docs/mac-app.md)
- [Release packaging and signing](docs/releases.md)
- [Pairing and authorization](docs/phone-control.md)
- [Domain terminology](GLOSSARY.md)
