# DDS Companion 0.8.0 — Public Preview

## Что нового

- Добавлен системный трей с действиями **Открыть DDS**, **Скрыть DDS** и **Выйти из DDS**.
- Добавлен автозапуск DDS вместе с Windows через стабильный корневой `DDS.exe`.
- Добавлен режим автозапуска только в системный трей: без главного окна, без кнопки на панели задач и без перехвата фокуса.
- Добавлена настройка **Кнопка закрытия → В трей**.
- Повторный запуск DDS восстанавливает уже запущенный экземпляр вместо запуска второго runtime.
- Tooltip значка в трее использует текущее Health-состояние DDS.

## Надёжность

- Полный выход через трей завершает Qt application и runtime чисто.
- Если системный трей недоступен, DDS запускается обычным видимым окном вместо скрытия без recovery surface.
- Автозапуск указывает на стабильный `DDS.exe`, а не на версионный `DDSApp.exe`.
- Архив, SQLite schema, DDS Plugin, media runtime и updater protocol этим релизом не менялись.

## Проверка

Accepted candidate: `4b691fe8369cf277e78a78323cb99c96b2fdeae7`.

- Windows CI: 184 tests × 3 — PASS.
- Native Windows build/package verification — PASS.
- Exact candidate live-tested on Windows.
- Tray-only autostart, close-to-tray, single-instance restore and clean exit validated.

Published full Windows ZIP SHA-256:
`09d92556d391328cfcf0618b0ab363c843e486bb6ee4bfd7cd97049ee6a7860c`

Published update ZIP SHA-256:
`f40b73bb6c8a80fa48063e288b79effe25d26f9df829ab96615afe0cf663149a`
