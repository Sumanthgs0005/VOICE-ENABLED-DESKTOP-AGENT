# LEO - Voice-Enabled Desktop Assistant

LEO is a voice-activated desktop assistant for Windows, built in Python. It's designed to help you with everyday tasks, answer questions, and control your system using voice commands.

This project integrates with Google for speech-to-text, Deepgram Aura for high-quality text-to-speech, and Google's Gemini AI for handling complex queries.

## 🚀 Features

* **Voice Activation:** Wakes up to the "Leo" hotword.
* **AI Integration:** Uses Google's Gemini AI for general knowledge, conversation, and complex questions.
* **Web & Search:**
    * Searches Google (e.g., "search for...")
    * Searches Wikipedia (e.g., "wikipedia...")
    * Plays YouTube videos (e.g., "play [song name]...")
    * Fetches real-time weather (e.g., "what's the weather in London?")
* **System Control (Windows):**
    * Adjusts system volume (e.g., "volume up", "volume down", "mute", "set volume 50")
    * Adjusts screen brightness (e.g., "brightness up", "brightness down")
    * Takes screenshots (e.g., "take a screenshot")
    * Manages power (e.g., "shutdown", "restart", "sleep")
* **Local File Search:**
    * Finds files on your computer (e.g., "find my resume")
    * Lists multiple matches and lets you open one by speaking the number.
* **Productivity & Fun:**
    * Tells you the time and date.
    * Tells jokes.
    * Checks system stats ("CPU usage", "RAM usage").

## 🛠️ Installation

This project is built for Windows, but many features (like web search and AI) will work on Mac/Linux.

### 1. Prerequisites

* **Python 3.8+**
* **Git**

### 2. Clone the Repository

```bash
git clone [https://github.com/your-username/leo-voice-assistant.git](https://github.com/your-username/leo-voice-assistant.git)
cd leo-voice-assistant
```

### 3. Install Required Libraries

The project depends on several Python libraries. You can install them all using the provided `requirements.txt` file (or create one).

**To create `requirements.txt`:**
```bash
pip freeze > requirements.txt
```
*(You may need to manually add libraries you've installed, like `pyttsx3`, `requests`, `SpeechRecognition`, `pycaw`, `google-generativeai`, `python-dotenv`, `pywhatkit`, `wikipedia`, `pyjokes`, `beautifulsoup4`, `psutil`, `Pillow`, `screen_brightness_control`, `winotify`, `plyer`, `simpleaudio`)*

**To install from `requirements.txt`:**
```bash
pip install -r requirements.txt
```

## ⚙️ Configuration (Crucial Step)

This project requires API keys to function. **Do not** write your keys directly in the code.

1.  Create a file named `.env` in the same project folder.

2.  Add your secret API keys to this `.env` file:
    ```
    GEMINI_API_KEY=AIzaSy...YOUR_GEMINI_KEY...
    DEEPGRAM_API_KEY=a7c1...YOUR_DEEPGRAM_KEY...
    ```

3.  **Get Your Keys:**
    * **Gemini (Google AI):** Get your key from [Google AI Studio](https://aistudio.google.com/app/apikey).
    * **Deepgram (Aura TTS):** Get your key from the [Deepgram Console](https://console.deepgram.com/).

The Python script uses `python-dotenv` to automatically load these keys.

## ▶️ How to Run

Once you have installed the libraries and configured your `.env` file, you can run the assistant from your terminal:

```bash
python LEO_FINAL.py
```

The script will initialize, and you'll see "Leo is now always listening..." when it's ready.

## 🗣️ Example Commands

* "Leo, what's the weather in Bengaluru?"
* "Leo, search Wikipedia for the Eiffel Tower."
* "Leo, play 'Never Gonna Give You Up' on YouTube."
* "Leo, volume up."
* "Leo, set volume to 40."
* "Leo, take a screenshot."
* "Leo, what's the time?"
* "Leo, tell me a joke."
* "Leo, find my project document."
* "Leo, how do you make a good first impression in an interview?" (This will be answered by Gemini AI)
* "Leo, shutdown."
