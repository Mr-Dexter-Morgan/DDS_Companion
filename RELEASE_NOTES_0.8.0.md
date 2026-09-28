# DDS Companion 0.8.0

Stable release, promoted from the live-validated Public Preview without rebuilding or replacing the accepted artifacts.

## Added

- Added a system tray surface with `Open DDS`, `Hide DDS`, and `Exit DDS` actions.
- Added persistent Windows autostart through the stable root `DDS.exe`.
- Added optional tray-only autostart: no main window, no taskbar button, and no foreground focus steal.
- Added optional `Close button -> Tray` behavior.
- Repeated DDS launches now restore the existing instance instead of starting a second runtime.
- Tray tooltip now follows the current DDS Health state.

## Reliability

- Explicit tray exit shuts down the Qt application and DDS runtime cleanly.
- If the Windows system tray is unavailable, DDS falls back to a normal visible startup.
- Windows autostart targets the stable root `DDS.exe`, never the versioned `DDSApp.exe`.

## Validation

- Exact accepted source commit: `4b691fe8369cf277e78a78323cb99c96b2fdeae7`.
- Windows CI: 184 tests × 3 passes, build and package verification passed.
- Windows live test: PASSED on the exact accepted candidate.
- Published full ZIP SHA-256: `09d92556d391328cfcf0618b0ab363c843e486bb6ee4bfd7cd97049ee6a7860c`.
- Published update ZIP SHA-256: `f40b73bb6c8a80fa48063e288b79effe25d26f9df829ab96615afe0cf663149a`.

## Compatibility

- No archive schema change.
- No DDS Plugin code change.
- No user-data migration.
- No media runtime or updater protocol change.
