"""
MacYandexMusicRPC — macOS port of WinYandexMusicRPC
"""

from mac_media import get_media_info, get_session_ids
from mac_autostart import is_in_autostart, toggle_autostart
from config_manager import ConfigManager
from itertools import permutations
from packaging import version
from datetime import timedelta
from yandex_music import Client, exceptions
from colorama import init, Fore, Style

import multiprocessing
import subprocess
import webbrowser
import pystray
import threading
import pypresence
import getToken
import keyring
import requests
import psutil
import json
import time
import re
import sys
import os
from enum import Enum
from PIL import Image

# ─── Discord app IDs ────────────────────────────────────────────────────────
CLIENT_ID_EN          = '1269807014393942046'   # Yandex Music
CLIENT_ID_RU          = '1217562797999784007'   # Яндекс Музыка
CLIENT_ID_RU_DECLINED = '1269826362399522849'   # Яндекс Музыку

# Отдельный Discord app для истории (тип PLAYING = попадает в Недавнюю активность)
# Это тот же CLIENT_ID_EN но мы будем использовать activity_type=PLAYING специально
CLIENT_ID_HISTORY = '1269807014393942046'

CURRENT_VERSION = "v2.5.1-mac"
REPO_URL = "https://github.com/FozerG/WinYandexMusicRPC"

# ─── Globals ────────────────────────────────────────────────────────────────
ya_token       = str()
strong_find    = True
auto_start_mac = False
show_history   = False

name_prev     = str()
result_queue  = multiprocessing.Queue()
needRestart   = False
iconTray      = None
config_manager = ConfigManager()


# ─── History RPC ─────────────────────────────────────────────────────────────
# При смене трека запускаем отдельный Python-процесс который на 35 сек
# показывает трек как "игру" (activity_type=PLAYING) → попадает в Недавнюю активность.
# Отдельный процесс нужен потому что два RPC не могут работать в одном процессе.

def _history_worker(client_id, title, artist, album, image, label):
    """Запускается в отдельном процессе."""
    try:
        import pypresence, time
        rpc = pypresence.Presence(client_id)
        rpc.connect()
        rpc.update(
            activity_type=0,   # PLAYING — именно этот тип пишется в Недавнюю активность
            details=title,
            state=artist,
            large_image=image,
            large_text=album,
        )
        time.sleep(35)
        rpc.clear()
        rpc.close()
    except Exception:
        pass


class HistoryRPC:
    _proc = None
    _lock = threading.Lock()

    @staticmethod
    def record(track: dict):
        if not show_history or not track or not track.get('success'):
            return

        with HistoryRPC._lock:
            # Завершить предыдущий если ещё жив
            if HistoryRPC._proc and HistoryRPC._proc.is_alive():
                HistoryRPC._proc.terminate()
                HistoryRPC._proc.join(timeout=2)

            p = multiprocessing.Process(
                target=_history_worker,
                args=(
                    CLIENT_ID_HISTORY,
                    track['title'],
                    track['artist'],
                    track['album'],
                    track['og-image'],
                    track['label'],
                ),
                daemon=True
            )
            p.start()
            HistoryRPC._proc = p
            log(f"History recorded: {track['label']}", LogType.Update_Status)

# ─── Enums ──────────────────────────────────────────────────────────────────

class ButtonConfig(Enum):
    YANDEX_MUSIC_WEB = 1
    YANDEX_MUSIC_APP = 2
    BOTH             = 3
    NEITHER          = 4

class ActivityTypeConfig(Enum):
    PLAYING   = 0
    LISTENING = 2

    def to_pypresence(self):
        try:
            from pypresence import ActivityType
            return {
                ActivityTypeConfig.PLAYING:   ActivityType.PLAYING,
                ActivityTypeConfig.LISTENING: ActivityType.LISTENING,
            }.get(self, ActivityType.PLAYING)
        except (ImportError, AttributeError):
            return self.value

class LanguageConfig(Enum):
    ENGLISH = 0
    RUSSIAN = 1

class PlaybackStatus(Enum):
    Unknown = 0
    Closed  = 1
    Opened  = 2
    Paused  = 3
    Playing = 4
    Stopped = 5

activityType_config = None
button_config       = None
language_config     = None

# ─── Localisation helper ─────────────────────────────────────────────────────

def t(en: str, ru: str) -> str:
    """Return Russian string when language is set to Russian."""
    return ru if language_config == LanguageConfig.RUSSIAN else en

# ─── macOS notification — removed (не нужны) ─────────────────────────────────

# ─── Presence ────────────────────────────────────────────────────────────────

class Presence:
    client       = None
    currentTrack = None
    rpc          = None
    running      = False
    paused       = False
    paused_time  = 0
    paused_elapsed = 0.0
    track_start_time = 0.0   # absolute time when track started (currentTime - elapsed)
    exe_names    = ["Discord", "DiscordCanary", "DiscordPTB", "Vesktop"]

    @staticmethod
    def is_discord_running() -> bool:
        for p in psutil.process_iter(['name']):
            try:
                if p.info['name'] in Presence.exe_names:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False

    @staticmethod
    def connect_rpc():
        try:
            client_id = (
                CLIENT_ID_EN if language_config == LanguageConfig.ENGLISH else
                CLIENT_ID_RU_DECLINED if activityType_config == ActivityTypeConfig.LISTENING else
                CLIENT_ID_RU
            )
            rpc = pypresence.Presence(client_id)
            rpc.connect()
            return rpc
        except pypresence.exceptions.DiscordNotFound:
            log("Pypresence - Discord not found.", LogType.Error)
        except pypresence.exceptions.InvalidID:
            log("Pypresence - Incorrect CLIENT_ID", LogType.Error)
        except Exception as e:
            log(f"Discord is not ready: {e}", LogType.Error)
        return None

    @staticmethod
    def discord_available():
        while True:
            if Presence.is_discord_running():
                Presence.rpc = Presence.connect_rpc()
                if Presence.rpc:
                    log("Discord готов к Rich Presence" if language_config == LanguageConfig.RUSSIAN
                        else "Discord is ready for Rich Presence")
                    break
                else:
                    log("Discord запущен, но ещё не готов. Повтор..." if language_config == LanguageConfig.RUSSIAN
                        else "Discord launched but not ready. Retrying...", LogType.Error)
            else:
                log("Discord не запущен" if language_config == LanguageConfig.RUSSIAN
                    else "Discord is not launched", LogType.Error)
            time.sleep(3)

    @staticmethod
    def stop():
        if Presence.rpc:
            try: Presence.rpc.close()
            except: pass
            Presence.rpc = None
        Presence.running = False

    @staticmethod
    def need_restart():
        log(t("Restarting RPC (settings changed)...",
              "Перезапуск RPC (настройки изменены)..."), LogType.Update_Status)
        global needRestart
        needRestart = True

    @staticmethod
    def restart():
        Presence.currentTrack = None
        global name_prev
        name_prev = None
        if Presence.rpc:
            try: Presence.rpc.close()
            except: pass
            Presence.rpc = None
        time.sleep(2)
        Presence.discord_available()

    @staticmethod
    def discord_was_closed():
        log(t("Discord was closed. Waiting for restart...",
              "Discord закрыт. Ожидание перезапуска..."), LogType.Error)
        Presence.currentTrack = None
        global name_prev
        name_prev = None
        Presence.discord_available()

    @staticmethod
    def start():
        global needRestart
        Presence.discord_available()
        if Presence.client:
            log(t("Initializing client with token...",
                  "Инициализация клиента с токеном..."))
        else:
            Presence.client = Client().init()
        Presence.running  = True
        Presence.currentTrack = None
        trackTime = 0

        while Presence.running:
            currentTime = time.time()

            if not Presence.is_discord_running():
                Presence.discord_was_closed()

            if needRestart:
                needRestart = False
                Presence.restart()

            try:
                ongoing_track = Presence.getTrack()

                # ── Track changed ────────────────────────────────────────────
                if Presence.currentTrack != ongoing_track:

                    if ongoing_track.get('success'):
                        label = ongoing_track['label']
                        prev_label = (Presence.currentTrack or {}).get('label')
                        if label != prev_label:
                            log(f"{t('Changed track to','Track changed to')} {label}",
                                LogType.Update_Status)
                            # Record previous track to history
                            if Presence.currentTrack and Presence.currentTrack.get('success'):
                                HistoryRPC.record(Presence.currentTrack)

                        Presence.paused        = False
                        Presence.paused_time   = 0
                        Presence.paused_elapsed = 0.0
                        trackTime = currentTime

                        # Calculate absolute track start from current position
                        elapsed_sec = ongoing_track['start-time'].total_seconds()
                        start_time  = currentTime - elapsed_sec
                        end_time    = start_time + ongoing_track['durationSec']
                        Presence.track_start_time = start_time  # remember for resume

                        args = _build_presence_args(ongoing_track, start_time, end_time)
                        Presence.rpc.update(**args)

                    else:
                        # Музыка остановилась — записать последний трек в историю
                        if Presence.currentTrack and Presence.currentTrack.get('success'):
                            HistoryRPC.record(Presence.currentTrack)
                        Presence.rpc.clear()
                        log(t("RPC cleared", "RPC очищен"))

                    Presence.currentTrack = ongoing_track

                # ── Same track ───────────────────────────────────────────────
                else:
                    if not ongoing_track.get('success'):
                        pass  # already cleared

                    elif ongoing_track["playback"] != PlaybackStatus.Playing.name and not Presence.paused:
                        # ── Just paused ──────────────────────────────────────
                        Presence.paused = True
                        Presence.paused_elapsed = ongoing_track['start-time'].total_seconds()
                        log(f"{t('Paused','На паузе')}: {ongoing_track['label']}",
                            LogType.Update_Status)

                        elapsed_sec = int(Presence.paused_elapsed)
                        pause_text  = (
                            f"{t('Paused','На паузе')} "
                            f"{format_duration(elapsed_sec*1000)} / "
                            f"{ongoing_track['formatted_duration']}"
                        )
                        args = _build_presence_args(
                            ongoing_track,
                            paused=True,
                            pause_text=pause_text
                        )
                        Presence.rpc.update(**args)

                    elif ongoing_track["playback"] == PlaybackStatus.Playing.name and Presence.paused:
                        # Resumed — recalculate start_time from real elapsed position
                        Presence.paused = False
                        log(f"{t('Resumed','Resumed')}: {ongoing_track['label']}",
                            LogType.Update_Status)

                        # Use actual elapsed from nowplaying-cli for accurate position
                        elapsed_sec = ongoing_track['start-time'].total_seconds()
                        start_time  = currentTime - elapsed_sec
                        end_time    = start_time + ongoing_track['durationSec']
                        Presence.track_start_time = start_time  # update saved time

                        args = _build_presence_args(ongoing_track, start_time, end_time)
                        Presence.rpc.update(**args)

                    elif ongoing_track["playback"] != PlaybackStatus.Playing.name and Presence.paused:
                        # ── Still paused — check 5-min timeout ───────────────
                        Presence.paused_time = currentTime - trackTime
                        if Presence.paused_time > 5 * 60:
                            trackTime = 0
                            Presence.rpc.clear()
                            log(t("RPC cleared (paused >5 min)",
                                  "RPC очищен (пауза >5 мин)"), LogType.Update_Status)

            except pypresence.exceptions.PipeClosed:
                Presence.discord_was_closed()
            except Exception as e:
                log(f"{t('Error','Ошибка')}: {e}", LogType.Error)

            time.sleep(1)   # 1s poll — faster track switching

    @staticmethod
    def getTrack() -> dict:
        global name_prev, strong_find
        try:
            info = get_media_info()   # direct sync call — no asyncio

            if not info:
                return {'success': False}

            artist   = info.get("artist", "").strip()
            title    = info.get("title",  "").strip()
            position = info['position']

            if not artist or not title:
                return {'success': False}

            name_current = f"{artist} - {title}"

            # Same track — just update position/playback state
            if name_current == name_prev:
                if Presence.currentTrack is None:
                    return {'success': False}
                copy = Presence.currentTrack.copy()
                copy["start-time"] = position
                copy["playback"]   = info['playback_status']
                return copy

            # New track — search in Yandex Music API
            log(f"{t('Now listening to','Сейчас слушает')}: {name_current}")
            name_prev = name_current

            if not Presence.client:
                return {'success': False}

            search = Presence.client.search(name_current.replace("'", " "), True, "all", 0, False)
            if search.tracks is None:
                search = Presence.client.search(name_current, True, "all", 0, False)
            if search.tracks is None:
                log(f"{t('Cannot find track','Трек не найден')}: {name_current}")
                return {'success': False}

            finalTrack = None
            debugStr   = []
            for idx, track in enumerate(search.tracks.results[:5], 1):
                if track.type not in ['music', 'track', 'podcast_episode']:
                    debugStr.append(f"  #{idx} wrong type")
                    continue
                artists = track.artists_name()
                variants = (
                    [', '.join(v) + " - " + track.title
                     for v in [list(p) for p in permutations(artists)]]
                    if len(artists) <= 4 else
                    [', '.join(artists) + " - " + track.title]
                )
                match = any(name_current.lower() == v.lower() for v in variants)
                if strong_find and not match:
                    debugStr.append(f"  #{idx} wrong title: {', '.join(artists)} - {track.title}")
                    continue
                finalTrack = track
                break

            if finalTrack is None:
                print('\n'.join(debugStr))
                log(f"{t('Not found (strong_find)','Не найдено (strong_find)')}: {name_current}")
                return {'success': False}

            t2 = finalTrack
            tid = t2.trackId.split(":")
            return {
                'success':            True,
                'title':              Single_char(TrimString(t2.title, 40)),
                'artist':             Single_char(TrimString(', '.join(t2.artists_name()), 40)),
                'album':              Single_char(TrimString(t2.albums[0].title, 25)),
                'label':              TrimString(f"{', '.join(t2.artists_name())} - {t2.title}", 50),
                'link':               f"https://music.yandex.ru/album/{tid[1]}/track/{tid[0]}/",
                'durationSec':        t2.duration_ms // 1000,
                'formatted_duration': format_duration(t2.duration_ms),
                'start-time':         position,
                'playback':           info['playback_status'],
                'og-image':           "https://" + t2.og_image[:-2] + "400x400",
            }

        except Exception as exc:
            Handle_exception(exc)
            return {'success': False}


# ─── Presence args builder ───────────────────────────────────────────────────

def _build_presence_args(track, start_time=None, end_time=None,
                         paused=False, pause_text=None) -> dict:
    is_ru = language_config == LanguageConfig.RUSSIAN
    args = {
        'activity_type': activityType_config.to_pypresence(),
        'details':       track['title'],
        'state':         track['artist'],
        'large_image':   track['og-image'],
    }
    if track['album'] != track['title']:
        args['large_text'] = track['album']

    if not paused and start_time and end_time:
        args['start'] = int(start_time)
        args['end']   = int(end_time)

    small_url = (
        "https://raw.githubusercontent.com/FozerG/WinYandexMusicRPC/main/assets/"
        + ("Paused.png" if paused else "Playing.png")
    )
    if activityType_config == ActivityTypeConfig.LISTENING or paused:
        args['small_image'] = small_url
        if paused and pause_text:
            args['small_text'] = pause_text
        else:
            args['small_text'] = t("Playing", "Проигрывается")

    if button_config != ButtonConfig.NEITHER:
        try:
            args['buttons'] = build_buttons(track['link'])
        except Exception:
            pass

    return args


# ─── Helpers ─────────────────────────────────────────────────────────────────

def format_duration(duration_ms):
    total = duration_ms // 1000
    return f"{total // 60}:{total % 60:02}"

def build_buttons(url):
    is_en = language_config == LanguageConfig.ENGLISH
    buttons = []
    if button_config in (ButtonConfig.YANDEX_MUSIC_WEB, ButtonConfig.BOTH):
        buttons.append({
            'label': 'Yandex Music (Web)' if is_en else 'Яндекс Музыка (браузер)',
            'url': url
        })
    if button_config in (ButtonConfig.YANDEX_MUSIC_APP, ButtonConfig.BOTH):
        dl = extract_deep_link(url)
        if dl:
            buttons.append({
                'label': 'Yandex Music (App)' if is_en else 'Яндекс Музыка (приложение)',
                'url': dl
            })
    # Discord button labels must be ≤32 bytes
    for b in buttons:
        if len(b['label'].encode('utf-8')) > 32:
            b['label'] = b['label'][:29] + '...'
    return buttons or None

def extract_deep_link(url):
    m = re.match(r"https://music\.yandex\.ru/album/(\d+)/track/(\d+)", url)
    if m:
        album_id, track_id = m.groups()
        return f"yandexmusic://album/{album_id}/track/{track_id}"
    return None

def Handle_exception(exc):
    s = str(exc).replace("'", '"')
    m = re.search(r'({.*?})', s)
    if m:
        s = m.group(1)
    try:
        data = json.loads(s)
        name = data.get('name', '')
        if name == 'Unavailable For Legal Reasons':
            log(t("Yandex Music unavailable in your region! Disable VPN or add token.",
                  "Яндекс Музыка недоступна в вашем регионе! Отключите VPN или добавьте токен."),
                LogType.Error)
            return
        if name == 'session-expired':
            log(t("Token expired. Please log in again.",
                  "Токен истёк. Войдите снова."), LogType.Error)
            return
    except Exception:
        pass
    log(f"{t('Error','Ошибка')}: {exc}", LogType.Error)

def TrimString(s, n): return s[:n] + "..." if len(s) > n else s
def Single_char(s):   return f'"{s}"' if len(s) == 1 else s

def Blur_string(s: str) -> str:
    if not s: return ''
    if len(s) <= 8: return s
    return s[:4] + '*' * (len(s) - 8) + s[-4:]


class LogType(Enum):
    Default       = 0
    Notification  = 1
    Error         = 2
    Update_Status = 3


def log(text, ltype=LogType.Default):
    init()
    colors = {
        LogType.Notification: Fore.YELLOW,
        LogType.Error:        Fore.RED,
        LogType.Update_Status:Fore.CYAN,
    }
    c = colors.get(ltype, Style.RESET_ALL)
    print(f"{Fore.RED}[MacYandexMusicRPC] -> {c}{text}{Style.RESET_ALL}")


def GetLastVersion(repoUrl):
    try:
        r = requests.get(repoUrl + '/releases/latest', timeout=5)
        r.raise_for_status()
        latest = r.url.split('/')[-1]
        cur = CURRENT_VERSION.replace("-mac", "")
        if version.parse(cur) < version.parse(latest):
            log(
                f"{t('New version available','Доступна новая версия')}: {latest} "
                f"({t('you have','у вас')} {CURRENT_VERSION}). "
                f"{t('Download','Скачать')}: {repoUrl}/releases/tag/{latest}",
                LogType.Notification
            )
            # NOTE: we just warn — we never auto-update to avoid Windows breakage
        else:
            log(t("Latest version installed.", "Установлена последняя версия."))
    except requests.exceptions.RequestException as e:
        log(f"{t('Cannot check updates','Не удалось проверить обновления')}: {e}", LogType.Error)


# ─── Settings ────────────────────────────────────────────────────────────────

def get_saves_settings(fromStart=False):
    global activityType_config, button_config, language_config
    global auto_start_mac, strong_find, show_history

    auto_start_mac = is_in_autostart()

    activityType_config = config_manager.get_enum_setting(
        'UserSettings', 'activity_type', ActivityTypeConfig,
        fallback=ActivityTypeConfig.LISTENING)
    button_config = config_manager.get_enum_setting(
        'UserSettings', 'buttons_settings', ButtonConfig,
        fallback=ButtonConfig.BOTH)
    language_config = config_manager.get_enum_setting(
        'UserSettings', 'language', LanguageConfig,
        fallback=LanguageConfig.ENGLISH)

    strong_find  = config_manager.get_setting(
        'UserSettings', 'strong_find', fallback='True').lower() == 'true'
    show_history = config_manager.get_setting(
        'UserSettings', 'show_history', fallback='False').lower() == 'true'

    if fromStart:
        log(
            f"Настройки: activityType={activityType_config.name}, "
            f"buttons={button_config.name}, language={language_config.name}, "
            f"strong_find={strong_find}, show_history={show_history}",
            LogType.Update_Status
        )


# ─── Tray ─────────────────────────────────────────────────────────────────────

def toggle_strong_find(item=None):
    global strong_find
    strong_find = not strong_find
    config_manager.set_setting('UserSettings', 'strong_find', str(strong_find))
    log(f"strong_find = {strong_find}")

def toggle_show_history(item=None):
    global show_history
    show_history = not show_history
    config_manager.set_setting('UserSettings', 'show_history', str(show_history))
    log(f"show_history = {show_history}")
    update_tray()

def toggle_auto_start_mac(item=None):
    global auto_start_mac
    auto_start_mac = not auto_start_mac
    log(f"auto_start = {auto_start_mac}")
    threading.Thread(target=lambda: toggle_autostart(auto_start_mac), daemon=True).start()

def get_account_name():
    try:
        u = Presence.client.me.account
        return u.display_name or "None"
    except exceptions.UnauthorizedError:
        return t("Invalid token", "Неверный токен")
    except exceptions.NetworkError:
        return t("Network error", "Ошибка сети")
    except Exception:
        return "None"

def convert_to_enum(cls, val):
    """Accept either an enum member or a string name."""
    if isinstance(val, cls):
        return val
    try:    return cls[str(val)]
    except: return None

def set_activity_type(val):
    v = convert_to_enum(ActivityTypeConfig, val)
    if v:
        config_manager.set_enum_setting('UserSettings', 'activity_type', v)
        get_saves_settings(); Presence.need_restart()

def set_button_config(val):
    v = convert_to_enum(ButtonConfig, val)
    if v:
        config_manager.set_enum_setting('UserSettings', 'buttons_settings', v)
        get_saves_settings(); Presence.need_restart()

def set_language_config(val):
    v = convert_to_enum(LanguageConfig, val)
    if v:
        config_manager.set_enum_setting('UserSettings', 'language', v)
        get_saves_settings(); Presence.need_restart(); update_tray()

# Friendly Russian names for enum values shown in menu
_BTN_NAMES = {
    'YANDEX_MUSIC_WEB': 'Браузер',
    'YANDEX_MUSIC_APP': 'Приложение',
    'BOTH':             'Оба',
    'NEITHER':          'Нет',
}
_ACT_NAMES = {
    'PLAYING':   'Играет',
    'LISTENING': 'Слушает',
}
_LANG_NAMES = {
    'ENGLISH': 'English',
    'RUSSIAN': 'Русский',
}

def _menu_label(enum_val):
    name = enum_val.name
    if language_config == LanguageConfig.RUSSIAN:
        return (
            _BTN_NAMES.get(name) or
            _ACT_NAMES.get(name) or
            _LANG_NAMES.get(name) or
            name
        )
    return name

def create_enum_menu(enum_class, get_func, set_func):
    return pystray.Menu(*(
        pystray.MenuItem(
            _menu_label(v),
            lambda item, v=v: set_func(v),
            checked=lambda item, v=v: get_func('UserSettings', enum_class) == v
        )
        for v in enum_class
    ))

def create_rpc_settings_menu():
    is_ru = language_config == LanguageConfig.RUSSIAN
    return pystray.Menu(
        pystray.MenuItem(
            t('Activity Type', 'Тип активности'),
            create_enum_menu(ActivityTypeConfig,
                lambda s,e: config_manager.get_enum_setting(s,'activity_type',e),
                set_activity_type)
        ),
        pystray.MenuItem(
            t('RPC Buttons', 'Кнопки RPC'),
            create_enum_menu(ButtonConfig,
                lambda s,e: config_manager.get_enum_setting(s,'buttons_settings',e),
                set_button_config)
        ),
        pystray.MenuItem(
            t('Language', 'Язык'),
            create_enum_menu(LanguageConfig,
                lambda s,e: config_manager.get_enum_setting(s,'language',e),
                set_language_config)
        ),
    )

def create_session_menu():
    try:    session_ids = get_session_ids()
    except: session_ids = []

    sel = config_manager.get_selected_session()
    items = [
        pystray.MenuItem(t('Refresh','Обновить'), lambda item: update_tray()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            t('Automatic','Автоматически'),
            lambda item: config_manager.set_selected_session("Automatic"),
            checked=lambda item: config_manager.get_selected_session() == "Automatic",
            radio=True
        ),
    ]
    for sid in session_ids:
        items.append(pystray.MenuItem(
            sid,
            (lambda s: lambda item: config_manager.set_selected_session(s))(sid),
            checked=(lambda s: lambda item: config_manager.get_selected_session() == s)(sid),
            radio=True
        ))
    return pystray.Menu(*items)

def build_tray_menu(icon=None):
    acc = get_account_name()

    yandex_menu = pystray.Menu(
        pystray.MenuItem(
            f"{t('Account','Аккаунт')}: {acc}",
            lambda item: None, enabled=False),
        pystray.MenuItem(
            t('Login to account...','Войти в аккаунт...'),
            lambda item: Init_yaToken(True)),
        pystray.MenuItem(
            t('Toggle strong_find','Строгий поиск'),
            toggle_strong_find,
            checked=lambda item: strong_find),
    )

    return pystray.Menu(
        pystray.MenuItem(
            t('Start with macOS','Автозапуск'),
            toggle_auto_start_mac,
            checked=lambda item: auto_start_mac),
        pystray.MenuItem(t('Yandex settings','Настройки Яндекса'), yandex_menu),
        pystray.MenuItem(t('RPC settings','Настройки RPC'), create_rpc_settings_menu()),
        pystray.MenuItem(t('Select App','Выбор приложения'), create_session_menu()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            t('Record to Recent Activity','Записывать в Недавнюю активность'),
            toggle_show_history,
            checked=lambda item: show_history),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("GitHub", lambda icon, item: webbrowser.open(REPO_URL, new=2)),
        pystray.MenuItem(t('Exit','Выход'), lambda icon, item: exit_app(icon)),
    )

def update_tray():
    global iconTray
    if iconTray is not None:
        iconTray.menu = build_tray_menu(iconTray)

def exit_app(icon, item=None):
    Presence.stop()
    if icon: icon.stop()
    os._exit(0)

def Get_IconPath():
    try:
        base = sys._MEIPASS if getattr(sys,'frozen',False) else os.path.dirname(os.path.abspath(__file__))
        for name in ("YMRPC_ico.png","YMRPC_ico.ico","pause.png"):
            p = os.path.join(base, "assets", name)
            if os.path.exists(p): return p
    except Exception:
        pass
    return None

def setup_tray(menu):
    global iconTray
    path = Get_IconPath()
    img  = Image.open(path) if path else Image.new('RGBA',(64,64),(88,101,242,255))
    icon = pystray.Icon("MacYandexMusicRPC", img, "MacYandexMusicRPC", menu=menu)
    iconTray = icon
    return icon


# ─── Token ────────────────────────────────────────────────────────────────────

def Remove_yaToken_From_Memory():
    try:
        if keyring.get_password('MacYandexMusicRPC','token'):
            keyring.delete_password('MacYandexMusicRPC','token')
            log(t("Old token removed.","Старый токен удалён."), LogType.Update_Status)
    except Exception: pass

def _token_task(icon_path, q):
    q.put(getToken.get_yandex_music_token(icon_path))

def Init_yaToken(forceGet=False):
    global ya_token
    token = ''

    if forceGet:
        try:
            Remove_yaToken_From_Memory()
            p = multiprocessing.Process(target=_token_task,
                                        args=(Get_IconPath(), result_queue))
            p.start()
            p.join(timeout=300)
            if p.is_alive():
                log(t("Token window timed out.","Окно токена не ответило."), LogType.Error)
                p.terminate(); p.join()
            token = result_queue.get_nowait() if not result_queue.empty() else ''
            if token and len(token) > 10:
                keyring.set_password('MacYandexMusicRPC','token', token)
                log(f"{t('Token saved','Токен сохранён')}: {Blur_string(token)}",
                    LogType.Update_Status)
        except Exception as e:
            log(f"{t('Token error','Ошибка токена')}: {e}", LogType.Error)
    else:
        if not ya_token:
            try:
                token = keyring.get_password('MacYandexMusicRPC','token') or ''
                if token:
                    log(f"{t('Loaded token','Токен загружен')}: {Blur_string(token)}",
                        LogType.Update_Status)
            except Exception as e:
                log(f"{t('Cannot load token','Не удалось загрузить токен')}: {e}", LogType.Error)
        else:
            token = ya_token
            log(f"{t('Token from script','Токен из скрипта')}: {Blur_string(token)}",
                LogType.Update_Status)

    if token and len(token) > 10:
        ya_token = token
        try:
            Presence.client = Client(token=ya_token).init()
            log(f"{t('Logged in as','Вошли как')} {get_account_name()}",
                LogType.Update_Status)
            update_tray()
        except Exception as e:
            Handle_exception(e)

    if not Presence.client:
        log(t("Continuing without token...","Работаем без токена..."))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    multiprocessing.freeze_support()

    log("MacYandexMusicRPC запускается...")
    GetLastVersion(REPO_URL)
    get_saves_settings(True)
    Init_yaToken(False)

    # Presence in background with watchdog
    def _watchdog():
        while True:
            th = threading.Thread(target=Presence.start, daemon=True)
            th.start()
            th.join()
            log(t("Presence thread crashed, restarting in 5s...",
                  "Поток Presence упал, перезапуск через 5с..."), LogType.Error)
            time.sleep(5)

    threading.Thread(target=_watchdog, daemon=True).start()

    # pystray MUST be on main thread on macOS
    icon = setup_tray(build_tray_menu())
    update_tray()
    try:
        icon.run()
    except KeyboardInterrupt:
        Presence.stop()
        icon.stop()
