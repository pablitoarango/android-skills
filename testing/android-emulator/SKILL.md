---
name: android-emulator
description: "Run and drive apps on emulators and devices with the Android CLI and adb: start and stop AVDs, install and launch APKs, inspect the UI with android layout, tap and type, screenshots, logcat, Gradle Managed Devices. Use when running, testing or debugging an app on a device, reading crash logs, or when adb shows offline or unauthorized devices or CI emulators lack a GPU."
---

# Android Emulator

Sources of truth: [Android CLI](https://developer.android.com/tools/agents/android-cli), [Run apps on the Android Emulator](https://developer.android.com/studio/run/emulator), [Start the emulator from the command line](https://developer.android.com/studio/run/emulator-commandline), [Android Debug Bridge (adb)](https://developer.android.com/tools/adb), [Logcat command-line tool](https://developer.android.com/tools/logcat), [Gradle Managed Devices](https://developer.android.com/studio/test/gradle-managed-devices).

Google deprecated the standalone `emulator` tool in favor of the Android CLI (`android`). Use `android` for emulators, deploying APKs, UI layout and screenshots, and `adb` for input, app state and logs.

## 1. Setup

- Check the tools: `android --version`, `android info` (prints the SDK path), `adb version`. If `android` is missing, install it from the [Android CLI page](https://developer.android.com/tools/agents); keep it current with `android update`.
- `android --sdk=<path>` overrides the SDK location; flags that should always apply can go in `~/.androidrc`, one per line.
- `android emulator` is currently disabled on Windows. There, start AVDs with the SDK's `emulator` binary (section 8).
- `--help` on a leaf command (`android emulator start --help`) prints the top-level help. `android help` prints the help of every command; `-v` adds verbose output for troubleshooting.
- The CLI changes quickly and its [reference page](https://developer.android.com/tools/agents/android-cli) can lag behind. When they disagree, trust `android help` for the installed version.

## 2. Emulators

```bash
android emulator list
android emulator create --list-profiles
android emulator create --profile=medium_phone
android emulator start medium_phone
adb devices -l
android emulator stop emulator-5554
android emulator remove medium_phone
```

- `android emulator start` returns only after the device has fully booted, so the next command can run right away.
- `stop` takes the **serial** (`emulator-5554`) from `adb devices`, not the AVD name.
- Each emulator uses a console and adb port pair: the first gets 5554/5555 and serial `emulator-5554`, the next `emulator-5556`, and so on.
- To stop an emulator through adb instead: `adb -s emulator-5554 emu kill`.
- Hardware acceleration: `emulator -accel-check` reports whether a hypervisor is installed. Without one the emulator is too slow for agent loops; use a physical device instead.

## 3. Devices

- With several devices connected, pass the serial to every command: `adb -s <serial> ...`, `android run --device=<serial>`, `android layout --device=<serial>`.
- `-s` takes precedence over `ANDROID_SERIAL`. `adb -e` targets the only emulator and `adb -d` the only USB device.
- A device in state `offline` or `unauthorized` in `adb devices` cannot take commands. For emulators, restart it; for physical devices, accept the debugging prompt.

## 4. Build, install and launch

`android run` installs and launches prebuilt APKs; `android install` only installs them. Neither builds.

```bash
./gradlew :app:assembleDebug
android run --apks=app/build/outputs/apk/debug/app-debug.apk
android run --apks=app-debug.apk --device=emulator-5554 --activity=.MainActivity
android install --apks=app-debug.apk --install-options=-g
```

- `android describe` lists the project's build targets and where their APKs are written, instead of guessing output paths.
- `--activity` is required when the app has more than one launchable activity.
- Both commands use delta installs by default, sending only changed code and resources. `--install-options` passes comma-separated package manager flags, for example `-g,-d`.
- Package manager install flags: `-r` reinstall keeping data, `-t` allow test APKs, `-g` grant all manifest permissions, `-d` allow a version-code downgrade.

App state:

| Goal | Command |
|---|---|
| Launch and wait for the first frame | `adb shell am start -W -n com.example.app/.MainActivity` |
| Cold restart | `adb shell am start -S -W -n com.example.app/.MainActivity` |
| Stop the app | `adb shell am force-stop com.example.app` |
| Reset app data | `adb shell pm clear com.example.app` |
| Grant or revoke a runtime permission | `adb shell pm grant com.example.app android.permission.POST_NOTIFICATIONS` |
| List third-party packages | `adb shell pm list packages -3` |
| Uninstall | `adb uninstall com.example.app` |

## 5. Inspect the UI

Use `android layout` first; it is faster and smaller than a screenshot.

```bash
android layout --pretty
android layout --flat --output=layout.json
android layout --full --pretty
```

The output is a JSON tree of interactive and text elements, nested under `children`. `--flat` returns a list instead. Each element can have `class`, `text`, `content-desc`, `resource-id` (with its package, like `com.example:id/title`), `interactions` (such as `CLICKABLE`, `FOCUSABLE`, `SCROLLABLE`, `EDITABLE`), `state` (such as `FOCUSED`, `CHECKED`, `SELECTED`), `bounds` (`[left,top][right,bottom]`) and `center` (`[x,y]`).

- The default output leaves out elements that are off-screen or hidden. `--full` includes them, plus non-interactive containers, marked with `off-screen` and `hidden`. It is several times larger, so use it only when an expected element is missing.
- Element order and property spelling have changed between CLI versions (older versions returned a flat list with lowercase values). Match on values, not positions, and compare `state` and `interactions` case-insensitively.
- `--no-idle` skips waiting for the UI to settle, for screens that animate constantly. `--diff` no longer does anything.
- Take a fresh layout after every action; coordinates from an old layout may point at something else.
- Content can load after an action. If an expected element is missing, wait a moment and fetch the layout again.
- `android layout` can fail while a WebView or animation is on screen. Fall back to an annotated screenshot:

```bash
android screen capture --annotate --output=screen.png
adb shell input $(android screen resolve --screenshot=screen.png --string="tap #12")
```

`--annotate` draws numbered boxes around elements; `screen resolve` replaces each `#N` with the center of box N. Always look at the PNG before choosing a number.

- Compose: test tags appear as `resource-id` only if the app sets `Modifier.semantics { testTagsAsResourceId = true }` near the root. Otherwise match Compose elements by text or content description.

## 6. Interact

`scripts/ui.py` finds an element in `android layout` and taps it or types into it. Matching on `--text` and `--desc` is a case-insensitive substring unless `--exact` is set; `--id` works with or without the `package:id/` prefix. It reads flat and tree layouts from any CLI version, waits up to `--timeout` seconds (default 10) for a match, skips off-screen and hidden elements, and refuses to act when several elements match until you pass `--index`.

```bash
python3 scripts/ui.py --text "Sign in"
python3 scripts/ui.py --text "Sign in" --tap
python3 scripts/ui.py --id email --type "user@example.com"
python3 scripts/ui.py --desc "Navigate up" --tap -s emulator-5556
```

`--type` taps the element, checks that something on screen gained focus, then types. Without `--tap` or `--type` it lists the matches.

Raw input with `adb shell input`:

| Action | Command |
|---|---|
| Tap | `adb shell input tap 540 1200` |
| Swipe or scroll (last argument is duration in ms) | `adb shell input swipe 540 1600 540 800 500` |
| Type into the focused field | `adb shell input text "Hello%sworld"` |
| Key event | `adb shell input keyevent KEYCODE_BACK` (`KEYCODE_HOME`, `KEYCODE_ENTER`, `KEYCODE_DEL`) |

- Scroll slowly (300 ms or more) so lists do not fling past the target. To reveal content further down, swipe from lower to higher on the screen.
- `input text` needs `%s` for spaces, and the text is parsed by both your shell and the device shell. `ui.py --type` handles both.
- adb 23+ quotes arguments like `ssh`: `adb shell setprop key "'two words'"` needs two levels of quotes.
- Check that a text field has `FOCUSED` in its `state` before typing.

## 7. Screenshots, recordings and logs

```bash
android screen capture --output=screen.png
adb exec-out screencap -p > screen.png
adb shell screenrecord --time-limit 30 /sdcard/demo.mp4
adb pull /sdcard/demo.mp4
```

`screenrecord` records at most 180 seconds, with no audio.

```bash
adb logcat -c
adb logcat --pid=$(adb shell pidof -s com.example.app)
adb logcat -d '*:E'
adb logcat -b crash -d
adb logcat MyTag:D '*:S'
```

- Clear the log before reproducing a bug, then read only what the reproduction produced.
- `--pid` needs the app to be running; after a crash its PID is gone, so read `-b crash` instead.
- `-d` dumps and exits; without it logcat streams until interrupted. Priorities are `V D I W E F S`; quote `*` so your shell does not expand it.

## 8. Headless and CI emulators

The Android CLI has no documented headless option. On CI or Windows, start the AVD with the SDK's `emulator` binary and wait for boot yourself:

```bash
"$ANDROID_HOME/emulator/emulator" -avd Pixel_8_API_35 -no-window -no-snapshot-load -no-boot-anim -no-audio &
adb wait-for-device
until [ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ]; do sleep 2; done
```

- `-no-snapshot-load` cold boots, `-no-snapshot-save` skips saving state on exit, `-no-snapshot` does both, `-wipe-data` resets to factory state.
- Leave `-gpu` on `auto`, which is the default and recommended mode; use `-gpu software` when hardware rendering fails. `swiftshader_indirect`, `swangle_indirect`, `guest`, `angle_indirect`, `angle` and `mesa` are deprecated.
- `-netfast` removes network throttling; `-netdelay` and `-netspeed` simulate slow networks.

## 9. Automated tests: Gradle Managed Devices

For instrumented tests, especially on CI, let Gradle create, boot and tear down the emulator instead of managing it yourself.

```kotlin
android {
    testOptions {
        managedDevices {
            localDevices {
                create("pixel6api34") {
                    device = "Pixel 6"
                    apiLevel = 34
                    systemImageSource = "aosp-atd"
                }
            }
            groups {
                create("phoneAndTablet") {
                    targetDevices.add(devices["pixel6api34"])
                }
            }
        }
    }
}
```

```bash
./gradlew pixel6api34DebugAndroidTest
./gradlew phoneAndTabletGroupDebugAndroidTest
./gradlew pixel6api34DebugAndroidTest -Pandroid.testoptions.manageddevices.emulator.gpu=swiftshader_indirect
```

- Task names are `<device><BuildVariant>AndroidTest` and `<group>Group<BuildVariant>AndroidTest`.
- On machines without hardware rendering (for example GitHub Actions runners), pass the GPU property shown above. It is the value the Gradle Managed Devices page documents, even though the emulator's own `-gpu swiftshader_indirect` flag is deprecated.
- Automated Test Device images (`aosp-atd`, `google-atd`) boot faster and use less CPU and memory. Use `google-atd` when tests need Google APIs. They disable hardware rendering, so they cannot run screenshot tests that depend on it.
- Shard across devices with `android.experimental.androidTest.numManagedDeviceShards=<n>` in `gradle.properties`.
- For a connected device or running emulator, use `./gradlew connectedDebugAndroidTest`.

## 10. Checklist

- [ ] Emulators are started and stopped with `android emulator` (or `emulator` plus a boot wait on CI and Windows).
- [ ] Every command targets an explicit serial when more than one device is connected.
- [ ] APKs come from a Gradle build and are deployed with `android run`.
- [ ] The UI is read with `android layout` before and after each action; screenshots are the fallback.
- [ ] Taps use coordinates from the current layout, never from memory.
- [ ] Logs are cleared before reproducing a bug and filtered by PID, tag or priority.
- [ ] Instrumented tests on CI use Gradle Managed Devices.
