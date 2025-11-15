# LEO – Voice-enabled desktop assistant (Windows-friendly)
# Features:
# - Always outputs BOTH text + voice in sync
# - Wake word "leo" + follow-up capture
# - STT via Google or Whisper (toggle)
# - TTS via Deepgram Aura (if configured) or pyttsx3 fallback
# - Windows toast / cross-platform notifications
# - Weather scraping, web open/search, YouTube play, Wikipedia summaries, jokes
# - System: volume (pycaw fixed), brightness, screenshot, sleep/restart/shutdown
# - File search: numbered results + spoken/typed selection, then open

import os
import io
import re
import sys
import time
import wave
import socket
import ctypes
import psutil
import threading
import datetime
import platform
import subprocess
import webbrowser
import requests
from bs4 import BeautifulSoup

# Audio / voice
import pyttsx3
import speech_recognition as sr
try:
    import simpleaudio as sa
except Exception:
    sa = None

# Optional extras
try:
    import screen_brightness_control as sbc
except Exception:
    sbc = None
try:
    from PIL import ImageGrab
except Exception:
    ImageGrab = None

# Windows volume control (pycaw) – FIXED
if platform.system().lower() == "windows":
    try:
        from ctypes import POINTER, cast           # cast from ctypes
        from comtypes import CLSCTX_ALL            # CLSCTX from comtypes
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except Exception:
        AudioUtilities = None
        IAudioEndpointVolume = None
        CLSCTX_ALL = None
else:
    AudioUtilities = None
    IAudioEndpointVolume = None
    CLSCTX_ALL = None

# Windows toast notifications
try:
    from winotify import Notification, audio as winotify_audio
except Exception:
    Notification = None
    winotify_audio = None

# Cross-platform notification fallback
try:
    from plyer import notification as plyer_notification
except Exception:
    plyer_notification = None

# = CONFIG FLAGS =
USE_WHISPER_STT = False            # Toggle to use local Whisper for STT (if installed)
USE_DEEPGRAM_TTS = True            # Toggle routing speech output through Deepgram Aura TTS
DG_TTS_MODEL = "aura-2"            # Deepgram latest model
DG_TTS_VOICE = "alloy"             # e.g., "alloy", "luna", etc.
DG_TTS_FORMAT = "wav"              # "wav" or "mp3"
WAKE_WORD = "leo"                  # Wake word

# = Gemini SDK =
try:
    from google import genai
    GEMINI_API_KEY = os.getenv("gemini-api-key", "").strip()
    if GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        gemini_client = None
except Exception:
    gemini_client = None

# = TTS (pyttsx3 fallback) =
engine = pyttsx3.init()
voices = engine.getProperty('voices')
if isinstance(voices, list) and len(voices) > 1:
    engine.setProperty('voice', voices[1].id)
engine.setProperty('rate', 165)
_engine_lock = threading.Lock()

def _tts_local_pyttsx3(text: str):
    with _engine_lock:
        engine.say(text)
        engine.runAndWait()

# = Deepgram Aura TTS =
DG_API_KEY = os.getenv("deepgram-api-key", "").strip()

def deepgram_tts_bytes(text: str, voice: str = DG_TTS_VOICE, model: str = DG_TTS_MODEL, fmt: str = DG_TTS_FORMAT) -> bytes:
    if not DG_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set.")
    url = "https://api.deepgram.com/v1/speak"
    params = {"model": model, "voice": voice, "format": fmt}
    headers = {
        "Authorization": f"Token {DG_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/wav" if fmt == "wav" else "audio/mpeg",
    }
    resp = requests.post(url, params=params, json={"text": text}, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.content

def _sa_play_wav_bytes(audio_bytes: bytes):
    if sa is not None:
        try:
            with io.BytesIO(audio_bytes) as bio:
                with wave.open(bio, "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    framerate = wf.getframerate()
            play_obj = sa.play_buffer(frames, channels, sampwidth, framerate)
            play_obj.wait_done()
            return
        except Exception:
            pass
    # Fallback: write temp file and open with OS
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        if platform.system().lower() == "windows":
            os.startfile(tmp)
        elif platform.system().lower() == "darwin":
            subprocess.run(["open", tmp])
        else:
            subprocess.run(["xdg-open", tmp])
    except Exception:
        pass

# = Notifications + unified output =
def _ascii_table(answer: str) -> str:
    now = datetime.datetime.now()
    time_str = now.strftime('%H:%M:%S')
    date_str = now.strftime('%B %d, %Y')
    oneline = answer.strip().replace("\n", " ")
    if len(oneline) > 220:
        oneline = oneline[:217] + "..."
    rows = [("Time", time_str), ("Date", date_str), ("Answer", oneline)]
    key_w = max(len(k) for k, _ in rows)
    val_w = max(len(v) for _, v in rows)
    top = "+-" + "-" * key_w + "-+-" + "-" * val_w + "-+"
    body = [top] + [f"| {k.ljust(key_w)} | {v.ljust(val_w)} |" for k, v in rows] + [top]
    return "\n".join(body)

def _toast(answer: str):
    now = datetime.datetime.now()
    title = "LEO – Reply"
    body = f"Time: {now.strftime('%H:%M:%S')}\nDate: {now.strftime('%B %d, %Y')}\n\n{answer}"
    if platform.system().lower() == "windows" and Notification is not None:
        try:
            toast = Notification(app_id="LEO Assistant", title=title, msg=body, icon=None, duration="short")
            if winotify_audio:
                toast.set_audio(winotify_audio.Default, loop=False)
            toast.show()
            return
        except Exception:
            pass
    if plyer_notification is not None:
        try:
            plyer_notification.notify(title=title, message=body, timeout=6)
            return
        except Exception:
            pass

def speak_and_print(text: str):
    """ALWAYS produce BOTH console text + voice (in sync)."""
    if not text:
        return
    print("\n" + _ascii_table(text) + "\n")
    _toast(text)
    if USE_DEEPGRAM_TTS and DG_API_KEY:
        try:
            audio_bytes = deepgram_tts_bytes(text)
            _sa_play_wav_bytes(audio_bytes)
            return
        except Exception as e:
            print(f"[Deepgram TTS fallback] {e}")
    _tts_local_pyttsx3(text)

# = Connectivity =
def is_connected() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except Exception:
        return False

# = Weather =
def fetch_weather_from_google(city: str) -> str:
    if not city.strip():
        return "Please specify a city."
    try:
        url = f"https://www.google.com/search?q=weather+{city.replace(' ', '+')}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        loc = soup.find("div", id="wob_loc")
        tim = soup.find("div", id="wob_dts")
        status = soup.find("span", id="wob_dc")
        temp = soup.find("span", id="wob_tm")
        precip = soup.find("span", id="wob_pp")
        hum = soup.find("span", id="wob_hm")
        wind = soup.find("span", id="wob_ws")
        if None in (loc, tim, status, temp, precip, hum, wind):
            return "Couldn't fetch weather details right now."
        return (f"Weather in {loc.text} at {tim.text}: {status.text}, "
                f"{temp.text}°C, precipitation {precip.text}, "
                f"humidity {hum.text}, wind {wind.text}.")
    except Exception as e:
        return f"Weather fetch error: {e}"

# = System controls =
def _get_endpoint_volume():
    if platform.system().lower() != "windows" or not AudioUtilities or not IAudioEndpointVolume or not CLSCTX_ALL:
        return None
    try:
        devices = AudioUtilities.GetSpeakers()
        # FIX: use _iid_ instead of iid
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        return volume
    except Exception:
        return None

def control_volume(action: str) -> str:
    volume = _get_endpoint_volume()
    if not volume:
        return "Volume control not supported."
    try:
        if action == "up":
            volume.SetMasterVolumeLevelScalar(min(volume.GetMasterVolumeLevelScalar() + 0.05, 1.0), None)
        elif action == "down":
            volume.SetMasterVolumeLevelScalar(max(volume.GetMasterVolumeLevelScalar() - 0.05, 0.0), None)
        elif action == "mute":
            volume.SetMute(1, None)
        elif action == "unmute":
            volume.SetMute(0, None)
        return f"Volume {action}."
    except Exception as e:
        return f"Volume error: {e}"

def set_volume_absolute(percent: int) -> str:
    volume = _get_endpoint_volume()
    if not volume:
        return "Volume control not supported."
    try:
        p = max(0, min(100, int(percent)))
        volume.SetMasterVolumeLevelScalar(p/100.0, None)
        return f"Volume set to {p}%."
    except Exception as e:
        return f"Volume error: {e}"

def take_screenshot():
    if ImageGrab is None:
        return None
    try:
        path = os.path.join(os.getcwd(), "screenshot.png")
        ImageGrab.grab().save(path)
        return path
    except Exception:
        return None

def set_brightness(level: int) -> bool:
    if sbc:
        try:
            sbc.set_brightness(max(0, min(100, int(level))))
            return True
        except Exception:
            return False
    return False

def system_sleep():
    if platform.system().lower() == "windows":
        try:
            ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
        except Exception:
            pass

def system_shutdown():
    if platform.system().lower() == "windows":
        subprocess.run(["shutdown", "/s", "/t", "1"])

def system_restart():
    if platform.system().lower() == "windows":
        subprocess.run(["shutdown", "/r", "/t", "1"])

# = STT =
recognizer = sr.Recognizer()
microphone = sr.Microphone()

def transcribe_google(audio: sr.AudioData) -> str:
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except Exception:
        return ""

def transcribe_whisper(audio: sr.AudioData) -> str:
    try:
        import tempfile
        import whisper
        model = whisper.load_model("base")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            wav_path = f.name
            wav_bytes = audio.get_wav_data(convert_rate=16000, convert_width=2)
            f.write(wav_bytes)
        result = model.transcribe(wav_path, fp16=False)
        try:
            os.unlink(wav_path)
        except Exception:
            pass
        return (result.get("text", "") or "").strip()
    except Exception:
        return ""

def recognize_once(timeout=None, phrase_time_limit=6) -> str:
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    text = transcribe_whisper(audio) if USE_WHISPER_STT else transcribe_google(audio)
    return (text or "").lower().strip()

# = Gemini =
def fetch_gemini_response(prompt: str) -> str:
    if gemini_client is None:
        return "Gemini not configured. Please ensure your API key is set in GEMINI_API_KEY."
    try:
        chat = gemini_client.chats.create(model="gemini-2.5-flash")
        response = chat.send_message(prompt)
        return (response.text or "(no response)").strip()
    except Exception as e:
        return f"Gemini AI error or no response: {e}"

# = File search utilities =
def search_files(keyword, search_path=None, extensions=None, max_results=20):
    if search_path is None:
        search_path = os.path.expanduser("~")
    matches = []
    key_lower = keyword.lower()
    for root, dirs, files in os.walk(search_path):
        for fname in files:
            if key_lower in fname.lower():
                if extensions and not any(fname.lower().endswith(ext.lower()) for ext in extensions):
                    continue
                matches.append(os.path.join(root, fname))
            if len(matches) >= max_results:
                return matches
    return matches

def open_file(file_path):
    try:
        if platform.system().lower() == "windows":
            os.startfile(file_path)
        elif platform.system().lower() == "darwin":
            subprocess.run(['open', file_path])
        else:
            subprocess.run(['xdg-open', file_path])
        return f"Opening: {file_path}"
    except Exception as e:
        return f"Failed to open {file_path}: {e}"

# Spoken number parsing for selection
WORD_NUMS = {
    "zero": 0, "oh": 0, "none": 0, "no": 0,
    "one": 1, "first": 1,
    "two": 2, "second": 2, "to": 2, "too": 2,
    "three": 3, "third": 3,
    "four": 4, "for": 4, "fourth": 4,
    "five": 5, "fifth": 5,
    "six": 6, "sixth": 6,
    "seven": 7, "seventh": 7,
    "eight": 8, "ate": 8, "eighth": 8,
    "nine": 9, "ninth": 9,
    "ten": 10, "tenth": 10,
}

def parse_spoken_number(s: str) -> int:
    s = (s or "").strip().lower()
    if not s:
        return -1
    m = re.search(r'\d+', s)
    if m:
        try:
            return int(m.group(0))
        except Exception:
            pass
    for t in re.split(r'\W+', s):
        if t in WORD_NUMS:
            return WORD_NUMS[t]
    return -1

def get_user_selection_via_voice_or_input(max_index: int) -> int:
    prompt = "I found multiple files. Please tell me the number of the file you'd like to open."
    speak_and_print(prompt)
    # Voice first
    try:
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=5)
        said = transcribe_whisper(audio) if USE_WHISPER_STT else transcribe_google(audio)
        sel = parse_spoken_number(said)
        if 0 <= sel <= max_index:
            return sel
    except Exception:
        pass
    # Fallback: typed input
    try:
        print("Enter the number of the file to open (0 to cancel):")
        sel = int(input("Your choice: ").strip())
        if 0 <= sel <= max_index:
            return sel
    except Exception:
        pass
    return -1

# = Command routing =
def process_command(q: str) -> str:
    q = q.lower().strip()

    # Greetings
    if q in ["hello", "hi", "hey", "good morning","good afternoon","good evening"]:
        return "Hello! How can I assist you?"
    if q in ["how are you", "how are you doing", "what's up", "whats up"]:
        return "I'm doing well, thank you! How can I help?"
    if q in ["bye", "exit", "quit", "goodbye", "stop"]:
        return "Goodbye!"

    # Wikipedia
    if "wikipedia" in q:
        try:
            import wikipedia
            topic = q.replace("search wikipedia for", "").replace("wikipedia", "").strip()
            return wikipedia.summary(topic, sentences=2)
        except Exception:
            return "Couldn't find that on Wikipedia."

    # Web/YT
    if "open youtube" in q:
        webbrowser.open("https://youtube.com"); return "Opening YouTube."
    if "open google" in q:
        webbrowser.open("https://google.com"); return "Opening Google."
    if q.startswith("search "):
        term = q.replace("search", "").strip()
        webbrowser.open(f"https://www.google.com/search?q={term}")
        return f"Searching Google for {term}."
    if q.startswith("play "):
        try:
            import pywhatkit
            song = q.replace("play", "").strip()
            pywhatkit.playonyt(song)
            return f"Playing {song}."
        except Exception:
            return "Couldn't play that right now."

    # Time/Date
    if "time" in q:
        return f"The time is {datetime.datetime.now().strftime('%H:%M:%S')}."
    if "date" in q:
        return f"Today's date is {datetime.datetime.now().strftime('%B %d, %Y')}."

    # Fun
    if "joke" in q:
        try:
            import pyjokes
            return pyjokes.get_joke()
        except Exception:
            return "I couldn't fetch a joke right now."

    # Weather
    if "weather" in q:
        city_match = re.search(r'weather (?:in|of)\s+(.+)', q)
        city = city_match.group(1) if city_match else ""
        return fetch_weather_from_google(city)

    # Volume control
    if re.search(r'\bvolume up\b', q): return control_volume("up")
    if re.search(r'\bvolume down\b', q): return control_volume("down")
    if "mute" in q and "unmute" not in q: return control_volume("mute")
    if "unmute" in q: return control_volume("unmute")
    # absolute volume: "set volume 45" or "volume 45"
    m = re.search(r'(?:set\s*)?volume\s*(\d{1,3})', q)
    if m:
        return set_volume_absolute(int(m.group(1)))

    # Brightness control
    if "brightness up" in q:
        if sbc:
            try:
                current_brightness = sbc.get_brightness()
                current = current_brightness[0] if isinstance(current_brightness, list) else current_brightness
                new_brightness = min(int(current) + 10, 100)
                set_brightness(new_brightness)
                return "Brightness increased."
            except Exception:
                return "Brightness control failed."
        else:
            return "Brightness control failed."
    if "brightness down" in q:
        if sbc:
            try:
                current_brightness = sbc.get_brightness()
                current = current_brightness[0] if isinstance(current_brightness, list) else current_brightness
                new_brightness = max(int(current) - 10, 0)
                set_brightness(new_brightness)
                return "Brightness decreased."
            except Exception:
                return "Brightness control failed."
        else:
            return "Brightness control failed."

    # Screenshot
    if "screenshot" in q:
        path = take_screenshot()
        return f"Screenshot saved to {path}" if path else "Screenshot failed."

    # System commands
    if "shutdown" in q: threading.Thread(target=system_shutdown).start(); return "Shutting down."
    if "restart" in q: threading.Thread(target=system_restart).start(); return "Restarting."
    if "sleep" in q: threading.Thread(target=system_sleep).start(); return "Sleeping now."

    # Internet check
    if "internet" in q: return "Connected." if is_connected() else "Not connected."

    # System stats
    if "cpu" in q: return f"CPU usage: {psutil.cpu_percent()}%"
    if "ram" in q: return f"RAM usage: {psutil.virtual_memory().percent}%"

    # File search commands
    file_keywords = [
        "find file", "search file", "fetch file", "open file",
        "find", "search", "fetch", "where", "locate", "show file", "get file"
    ]
    if any(k in q for k in file_keywords):
        # Extract search terms
        words = q
        for k in file_keywords:
            words = words.replace(k, "")
        search_terms = words.strip()
        if not search_terms or len(search_terms) < 2:
            return "Please specify a file name, keyword, or part of it to search."
        matches = search_files(search_terms)
        if not matches:
            return f"No files found matching '{search_terms}'."
        if len(matches) == 1:
            chosen_file = matches[0]
            open_result = open_file(chosen_file)
            return f"Found and {open_result}"
        else:
            # List results
            lines = ["Files found:"]
            for idx, path in enumerate(matches, 1):
                lines.append(f"{idx}. {path}")
            print("\n" + "\n".join(lines) + "\n")
            # Ask & select (voice or typed)
            sel = get_user_selection_via_voice_or_input(len(matches))
            if sel == 0:
                return "Cancelled. No file opened."
            if 1 <= sel <= len(matches):
                chosen_file = matches[sel - 1]
                open_result = open_file(chosen_file)
                return f"Opened: {chosen_file}"
            else:
                return "Invalid choice. No file opened."

    # Default: Gemini AI
    return fetch_gemini_response(q)

def handle_query(query: str):
    response = process_command(query)
    print(f"User: {query}")
    print(f"Leo: {response}")
    speak_and_print(response)

# = Always-listen loop with wake word =
def listen_for_wake_word():
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
    print("Leo is now always listening. Say 'Leo' to activate.")
    while True:
        with microphone as source:
            try:
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=5)
                said = transcribe_whisper(audio) if USE_WHISPER_STT else transcribe_google(audio)
                said = (said or "").lower().strip()
                if not said:
                    continue
                if WAKE_WORD in said:
                    query = said.split(WAKE_WORD, 1)[1].strip()
                    if not query:
                        speak_and_print("Yes?")
                        audio2 = recognizer.listen(source, timeout=6, phrase_time_limit=8)
                        query = transcribe_whisper(audio2) if USE_WHISPER_STT else transcribe_google(audio2)
                        query = (query or "").lower().strip()
                    if query:
                        handle_query(query)
            except sr.UnknownValueError:
                continue
            except Exception as e:
                print("Error listening:", e)

# = MAIN =
if __name__ == "__main__":
    try:
        listen_for_wake_word()
    except KeyboardInterrupt:
        print("\nExiting LEO. Bye!\n")
        speak_and_print("Exiting LEO. Bye!")
