---
name: android-emulator
description: "Run and drive apps on emulators and devices with the Android CLI and adb: start and stop AVDs, install and launch APKs, inspect the UI with android layout, tap and type with android input, screenshots, logcat, Gradle Managed Devices. Use when running, testing or debugging an app on a device, reading crash logs, or when adb shows offline or unauthorized devices or CI emulators lack a GPU."
---

# Android Emulator

Sources of truth: [Android CLI](https://developer.android.com/tools/agents/android-cli), [Android CLI command reference](https://developer.android.com/tools/agents/android-cli/commands), [android input](https://developer.android.com/tools/agents/android-cli/commands/input), [Run apps on the Android Emulator](https://developer.android.com/studio/run/emulator), [Start the emulator from the command line](https://developer.android.com/studio/run/emulator-commandline), [Android Debug Bridge (adb)](https://developer.android.com/tools/adb), [Logcat command-line tool](https://developer.android.com/tools/logcat), [Gradle Managed Devices](https://developer.android.com/studio/test/gradle-managed-devices) (now called build-managed devices), [Configure hardware acceleration](https://developer.android.com/studio/run/emulator-acceleration).

Google deprecated the standalone `emulator` tool in favor of the Android CLI (`android`). Use `android` for emulators, building and deploying, UI layout, input and screenshots, and `adb` for app state and logs.

## 1. Setup

- Check the tools: `android --version`, `android info` (prints the SDK path), `adb version`. If `android` is missing, install it from the [Android CLI page](https://developer.android.com/tools/agents); keep it current with `android update`.
- This skill follows Android CLI 1.1 as documented. CLI 1.0 lacks some commands and flags (`android input`, `android build`, `emulator start --headless`), so run `android update` if `android --version` reports 1.0.
- `android --sdk=<path>` overrides the SDK location; flags that should always apply can go in `~/.androidrc`, one per line.
- `android help <command>` or `<command> --help` (for example `android emulator start --help`) prints the help of one command; `android help` prints all of them. `-v` adds verbose output for troubleshooting.
- The CLI changes quickly and its [command reference](https://developer.android.com/tools/agents/android-cli/commands) can lag behind. When they disagree, trust `android help` for the installed version.

## 2. Emulators

```bash
android emulator list --long
android emulator create --list-profiles
android emulator create medium_phone
android emulator start medium_phone
adb devices -l
android emulator stop emulator-5554
android emulator remove medium_phone
```

- `android emulator create` without a profile creates `medium_phone`.
- `android emulator start` returns only after the device has fully booted, so the next command can run right away. `--cold` skips the quick-boot snapshot; `--headless` runs without a window.
- `list --long` shows each AVD's API level, status and serial.
- `stop` takes the AVD name or the serial (`emulator-5554`), and needs neither when only one emulator is running.
- `remove --force` deletes a leftover `.ini` whose `.avd` directory is already gone.
- Each emulator uses a console and adb port pair: the first gets 5554/5555 and serial `emulator-5554`, the next `emulator-5556`, and so on.
- To stop an emulator through adb instead: `adb -s emulator-5554 emu kill`.
- Hardware acceleration: `emulator -accel-check` reports whether a hypervisor is installed. Without one the emulator is too slow for agent loops; use a physical device instead.

## 3. Devices

- With several devices connected, pass the serial to every command: `adb -s <serial> ...`, `android run --device=<serial>`, `android layout --device=<serial>`, `android input --device=<serial> tap ...`.
- `-s` takes precedence over `ANDROID_SERIAL`. `adb -e` targets the only emulator and `adb -d` the only USB device.
- A device in state `offline` or `unauthorized` in `adb devices` cannot take commands. For emulators, restart it; for physical devices, accept the debugging prompt.

## 4. Build, install and launch

`android run` installs and launches an app; `android install` only installs it. Both take either a build reference such as `:app` (built first, like `android build :app`) or prebuilt APKs with `--apks`. Arguments after `--` go to the build system.

```bash
android run :app
android build :app@debug
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

The output is JSON with the visible text, resource IDs, content descriptions, interaction states and bounds of each element. `--flat` returns a list instead of a tree. In current versions elements typically carry `class`, `text`, `content-desc`, `resource-id` (like `com.example:id/title`), `interactions`, `state`, `bounds` and `center`; Google does not document the schema and it has changed between versions, so match on values rather than positions or exact spelling.

- The default output leaves out non-interactive and hidden elements. `--full` includes them; it is much larger, so use it only when an expected element is missing.
- `--no-idle` skips waiting for the UI thread to go idle, for screens that animate constantly. `--diff` does nothing and will be removed.
- Take a fresh layout after every action; coordinates from an old layout may point at something else.
- When `android layout` cannot see an element (in practice this happens with some WebViews and custom-drawn views), fall back to an annotated screenshot:

```bash
android screen capture --annotate --output=screen.png
adb shell $(android screen resolve --screenshot=screen.png --string="input tap #12")
```

`--annotate` draws numbered boxes around detected elements; `screen resolve` replaces each `#N` with the center of box N. Always look at the PNG before choosing a number.

- Compose: test tags appear as `resource-id` only if the app sets `Modifier.semantics { testTagsAsResourceId = true }` near the root. Otherwise match Compose elements by text or content description.

## 6. Interact

`android input` finds an element by selector in the live UI and acts on it:

```bash
android input tap 'text=Sign in'
android input tap 'desc=Navigate up' --device=emulator-5556
android input text 'user@example.com' 'id=email' --submit
android input scroll 'id=recycler_view' --dir=down --until='text=Settings'
android input swipe 'id=card' --dir=left
android input key back
```

- A selector is a comma-separated list of `key=value` pairs that must all match. String keys are `text`, `id`, `class` and `desc`; they match as case-insensitive substrings, and `/regex/` (add `i` for case-insensitive) matches by regular expression, for example `'text=/^Sign in$/'`. Boolean keys include `clickable`, `scrollable`, `focusable`, `checked`, `focused` and `selected`.
- Quote selectors in single quotes so the shell leaves spaces and commas alone.
- By default (`--match=single`) a selector that matches several elements fails and lists them; narrow the selector, or pass `--match=first` when the first match is the right one.
- `--wait=<ms>` waits for the target to appear, for content that loads after an action.
- `input text` replaces the field's current text. `input key` takes names like `back`, `home`, `enter`, `tab` or an Android keycode.
- `input scroll --until` scrolls a container until the target is on screen; use it before tapping elements that are further down a list.

Raw input with `adb shell input`, for coordinates from `screen resolve` or elements `android input` cannot target:

| Action | Command |
|---|---|
| Tap | `adb shell input tap 540 1200` |
| Swipe (last argument is duration in ms) | `adb shell input swipe 540 1600 540 800 500` |
| Type into the focused field | `adb shell input text "Hello%sworld"` |
| Key event | `adb shell input keyevent KEYCODE_BACK` |

- `adb shell input text` needs `%s` for spaces, and the text is parsed by both your shell and the device shell. adb 23+ quotes arguments like `ssh`: `adb shell setprop key "'two words'"` needs two levels of quotes.

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

On CI, start the AVD without a window and from a cold boot; `android emulator start` waits for boot itself:

```bash
android emulator start --headless --cold medium_phone
```

When you need emulator flags the CLI does not expose, start the SDK's `emulator` binary directly and wait for boot yourself:

```bash
"$ANDROID_HOME/emulator/emulator" -avd medium_phone -no-window -no-snapshot-load -no-boot-anim -no-audio &
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
                create("pixel6api30") {
                    device = "Pixel 6"
                    apiLevel = 30
                    systemImageSource = "aosp-atd"
                }
            }
            groups {
                create("phoneAndTablet") {
                    targetDevices.add(devices["pixel6api30"])
                }
            }
        }
    }
}
```

```bash
./gradlew pixel6api30DebugAndroidTest
./gradlew phoneAndTabletGroupDebugAndroidTest
./gradlew pixel6api30DebugAndroidTest -Pandroid.testoptions.manageddevices.emulator.gpu=swiftshader_indirect
```

- Task names are `<device><BuildVariant>AndroidTest` and `<group>Group<BuildVariant>AndroidTest`.
- On machines without hardware rendering (for example GitHub Actions runners), pass the GPU property shown above. It is the value the build-managed devices page documents, even though the emulator's own `-gpu swiftshader_indirect` flag is deprecated.
- Automated Test Device images (`aosp-atd`, `google-atd`) use less CPU and memory. Google documents them for API level 30 only; use `google-atd` when tests need Google Play Services. They disable hardware rendering, so they cannot run screenshot tests that depend on it.
- Shard across devices with `android.experimental.androidTest.numManagedDeviceShards=<n>` in `gradle.properties`.
- For a connected device or running emulator, use `./gradlew connectedDebugAndroidTest`.

## 10. Checklist

- [ ] Emulators are started and stopped with `android emulator`, with `--headless` on CI.
- [ ] Every command targets an explicit serial when more than one device is connected.
- [ ] Apps are built and deployed with `android run` (a build reference or Gradle-built APKs).
- [ ] The UI is read with `android layout` before and after each action; screenshots are the fallback.
- [ ] Taps and typing go through `android input` selectors; raw coordinates come from the current layout or `screen resolve`, never from memory.
- [ ] Logs are cleared before reproducing a bug and filtered by PID, tag or priority.
- [ ] Instrumented tests on CI use Gradle Managed Devices.
