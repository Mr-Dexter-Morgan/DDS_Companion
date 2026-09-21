# DDS — Discord Data Snatcher
## DDS Companion 0.6.1 candidate

0.6.1 is the polish/UX follow-up to the 0.6.0 native Windows EXE and DataRoot foundation.

### Product identity
- Product: **DDS — Discord Data Snatcher**
- Executable: **DDS.exe**
- Internal component: DDS Companion
- AppUserModelID: `DDS.DiscordDataSnatcher.Companion`

### Main 0.6.1 changes
- full local archive reset with settings preserved;
- reset boundary preventing old untouched DDS_Data captures from instantly rebuilding a deliberately cleared archive;
- expired Discord signed URLs automatically move to passive rediscovery instead of requiring routine Ignore All;
- fresh observation of the same stable attachment restores it automatically;
- semantic storage delta wording after cache cleanup;
- public GUI naming/title cleanup;
- additional reset/recovery regression coverage.

### One intentionally unresolved product decision
The earlier note `только кэш / только текст / как выбрано в Библиотеке` has not been wired to local import yet. The current Library `Выгрузка` switches are explicitly future-export rules. Reusing them as import filters would couple export policy to local archive retention. Confirm the intended boundary before implementation.

### Windows build
Run:

`build_windows.bat`

Expected product:

`dist\DDS\DDS.exe`

The build stays **onedir** for inspection and live validation.

### Validation
Automated gate: **106/106 PASS ×3** in source and extracted package, `compileall` PASS, CLI version PASS.
Windows 0.6.1 live validation is still required before local acceptance.
GitHub publication is deliberately deferred.
