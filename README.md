# <img src="./assets/pause.png" alt="[DISCORD RPC]" width="30"/> &nbsp;MacYandexMusicRPC

[![OS - macOS](https://img.shields.io/badge/OS-macOS-black?logo=apple&logoColor=white)](https://github.com/FozerG/WinYandexMusicRPC)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Based on](https://img.shields.io/badge/Based%20on-WinYandexMusicRPC-red)](https://github.com/FozerG/WinYandexMusicRPC)

> macOS-порт [WinYandexMusicRPC](https://github.com/FozerG/WinYandexMusicRPC) by **[FozerG](https://github.com/FozerG)**.  
> Оригинальный проект использует `Windows.Media.Control` — этот порт заменяет его на `nowplaying-cli` / AppleScript и адаптирует всё под macOS.

**Discord Rich Presence для Яндекс Музыки на macOS. Показывает текущий трек, обложку и прогресс прямо в вашем профиле Discord.**

<img src="https://github.com/user-attachments/assets/99d15c70-632f-41ec-a6cd-49de8a7d2a8f" alt="discord" width="340">

## Плюсы

| Функция | Статус |
|---|---|
| Не нужен токен Яндекс Музыки (базовый режим) | ✅ |
| Показывает треки из радио и подборок | ✅ |
| Работает с браузером и приложением Яндекс Музыки | ✅ |
| Показывает статус паузы | ✅ |
| Показывает сколько осталось до конца трека | ✅ |
| Статус «Слушает» вместо «Играет в игру» | ✅ |
| Иконка в меню-баре (без Dock) | ✅ |
| Автозапуск через LaunchAgent | ✅ |
| Запись прослушанных треков в «Недавнюю активность» Discord | ✅ |

## Требования

- macOS 11 (Big Sur) или новее
- Python 3.10 – 3.13
- Discord (десктоп)
- `nowplaying-cli` (рекомендуется): `brew install nowplaying-cli`

## Установка и запуск

### 1. Установить зависимости

```bash
pip install -r requirements.txt
brew install nowplaying-cli   # для надёжного чтения Now Playing
```

### 2. Запустить

```bash
python main.py
```

Скрипт автоматически уйдёт в меню-бар (иконка в трее).  
Яндекс Музыку можно слушать в браузере или в приложении.

## Токен Яндекс Музыки (опционально, но рекомендуется)

Без токена некоторые треки могут не находиться из-за региональных ограничений API.

**Получить токен:**
1. Открой в браузере:
   ```
   https://oauth.yandex.ru/authorize?response_type=token&client_id=23cabbbdc6cd418abb4b39c32c41195d
   ```
2. Войди в аккаунт Яндекс Музыки
3. Скопируй значение `access_token=...` из адресной строки (только сам токен, без `access_token=` и без `&...`)
4. Вставь в `main.py`:
   ```python
   ya_token = "y0__твой_токен_здесь"
   ```

Либо используй меню-бар: **Yandex settings → Login to account...**

> ⚠️ Никому не передавайте токен — он даёт доступ к аккаунту Яндекса.

## Настройки в меню-баре

| Пункт | Описание |
|---|---|
| Autostart | Автозапуск при входе в macOS |
| Yandex settings | Токен, строгий поиск |
| RPC settings → Activity Type | «Слушает» или «Играет» |
| RPC settings → RPC Buttons | Кнопки в профиле Discord |
| RPC settings → Language | English / Русский |
| Select App | Выбрать источник воспроизведения |
| Record to Recent Activity | Записывать треки в «Недавнюю активность» Discord |

## Компиляция в .app

```bash
pip install pyinstaller
pyinstaller --noconfirm MacYandexMusicRPC.spec
```

Готовое приложение появится в папке `dist/MacYandexMusicRPC.app`.  
Его можно перенести в `/Applications` и запускать как обычное macOS-приложение.

## Отличия от оригинала (Windows → macOS)

| Компонент | WinYandexMusicRPC | MacYandexMusicRPC |
|---|---|---|
| Чтение Now Playing | `winrt` / `Windows.Media.Control` | `nowplaying-cli` + AppleScript |
| Автозапуск | Реестр / папка Startup | LaunchAgent plist |
| Конфиг | `%LOCALAPPDATA%` | `~/Library/Application Support/` |
| Сборка | InnoScript + `.exe` | PyInstaller `.app` |
| Windows-зависимости | `pywin32`, `winreg`, `winrt-*` | Удалены |

## Баги

Нашёл ошибку? Создай [Issue](../../issues) — постараюсь исправить.

---

> Основан на [WinYandexMusicRPC](https://github.com/FozerG/WinYandexMusicRPC) by [FozerG](https://github.com/FozerG).  
> Используется [Yandex Music API](https://github.com/MarshalX/yandex-music-api).
