# DDS — Discord Data Snatcher
## DDS Companion 0.6.0 candidate

0.6.0 is the first Application Foundation milestone after the verified 0.5.8 prototype.

### Product identity
- Product: **DDS — Discord Data Snatcher**
- Executable: **DDS.exe**
- Approved application artwork: `assets/DDS.ico`
- Windows AppUserModelID: `DDS.DiscordDataSnatcher.Companion`

### DataRoot profiles
Installed mode preserves the existing data root:

`%LOCALAPPDATA%\DDS_Companion`

Portable foundation:

`DDS.exe` + `Data\config`, `Data\database`, `Data\media`, `Data\cache`, `Data\logs`, `Data\backups`

The archive schema and application services are shared between both profiles. Only the resolved DataRoot changes.

### Build Windows onedir candidate
Run:

`build_windows.bat`

Expected output:

`dist\DDS\DDS.exe`

The build is intentionally **onedir** for the 0.6.0 inspection/live gate. Onefile packaging is not the target of this milestone.

### Validation
Automated source gate: **101/101 PASS**. Native Windows EXE and real archive live validation are still required before promotion/release.
