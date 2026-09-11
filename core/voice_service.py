import os
import io
import math
import struct
import wave
import asyncio
import tempfile
import threading
import queue
import time
import re
from pathlib import Path
from typing import Callable, Optional
import speech_recognition as sr

# Suppress pygame banner
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

class VoiceService:
    """
    High-fidelity Neural AI Voice Service.
    Uses Microsoft Neural Edge TTS (en-US-AriaNeural) for an impressive, crystal-clear,
    natural female voice, with offline SAPI fallback, sound effect cues, and non-blocking playback.
    """

    FEMALE_VOICE = "en-US-AriaNeural" # Impressive, clear, confident female AI assistant voice

    MODE_LINES = {
        "Auto (Hybrid)": "Hybrid intelligence mode activated.",
        "Docs Only": "Document search mode activated.",
        "Web Only": "Live web search mode activated."
    }

    def __init__(self):
        self.is_listening = False
        self._stt_thread: Optional[threading.Thread] = None
        self._tts_queue = queue.Queue()
        self._tts_thread: Optional[threading.Thread] = None
        self._tts_speaking = False
        self._stop_tts_event = threading.Event()

        # Audio Cache Dir
        self.cache_dir = Path(tempfile.gettempdir()) / "ai_studio_audio_v2"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Sound Cue Objects
        self._snd_mic_on: Optional[pygame.mixer.Sound] = None
        self._snd_mic_off: Optional[pygame.mixer.Sound] = None

        # Init Pygame Mixer for smooth, low-latency audio
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except Exception as e:
            print(f"Mixer Init: {e}")

        # Initialize and load mic sound cues
        self._init_sound_effects()

        # Start background TTS loop
        self._init_tts_worker()

        # Pre-cache mode announcement audio files in background
        threading.Thread(target=self._precache_mode_audio, daemon=True).start()

    def _init_sound_effects(self):
        """Generates and loads acoustic sound effect cues for microphone ON/OFF."""
        try:
            on_path = self.cache_dir / "mic_on.wav"
            off_path = self.cache_dir / "mic_off.wav"

            if not on_path.exists() or on_path.stat().st_size == 0:
                self._generate_chime_wav(
                    on_path,
                    tones=[(523.25, 0.08, 0.35), (783.99, 0.13, 0.45)], # Ascending C5 -> G5
                    decay=4.5
                )

            if not off_path.exists() or off_path.stat().st_size == 0:
                self._generate_chime_wav(
                    off_path,
                    tones=[(659.25, 0.08, 0.35), (440.00, 0.12, 0.30)], # Descending E5 -> A4
                    decay=5.0
                )

            if pygame.mixer.get_init():
                self._snd_mic_on = pygame.mixer.Sound(str(on_path))
                self._snd_mic_off = pygame.mixer.Sound(str(off_path))
        except Exception as e:
            print(f"Sound Effects Init Notice: {e}")

    def _generate_chime_wav(self, file_path: Path, tones: list, decay: float = 4.5):
        """Synthesizes smooth harmonic chime WAV audio without clicks or pops."""
        sample_rate = 44100
        frames = bytearray()
        for freq, duration, max_amp in tones:
            num_samples = int(sample_rate * duration)
            for i in range(num_samples):
                t = float(i) / sample_rate
                # Smooth attack (15ms) and exponential decay envelope
                env = (math.sin(math.pi * i / (sample_rate * 0.015)) if i < sample_rate * 0.015 else 1.0) * math.exp(-decay * t / duration)
                sample = int(32767.0 * max_amp * env * (0.85 * math.sin(2 * math.pi * freq * t) + 0.15 * math.sin(4 * math.pi * freq * t)))
                sample = max(-32767, min(32767, sample))
                frames.extend(struct.pack('<h', sample))

        with wave.open(str(file_path), 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(frames)

    def play_mic_on(self):
        """Plays immediate crisp ascending chime cue when microphone starts listening."""
        try:
            if self._snd_mic_on:
                self._snd_mic_on.play()
        except Exception as e:
            print(f"Mic On Play Notice: {e}")

    def play_mic_off(self):
        """Plays immediate soft descending chime cue when microphone stops listening."""
        try:
            if self._snd_mic_off:
                self._snd_mic_off.play()
        except Exception as e:
            print(f"Mic Off Play Notice: {e}")

    def _init_tts_worker(self):
        self._tts_thread = threading.Thread(target=self._tts_loop, daemon=True)
        self._tts_thread.start()

    def _precache_mode_audio(self):
        """Generates and saves calm, natural neural female mode activation audio clips."""
        try:
            import edge_tts
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def generate_clips():
                for mode_key, text in self.MODE_LINES.items():
                    safe_name = mode_key.replace(" ", "_").replace("(", "").replace(")", "").lower()
                    file_path = self.cache_dir / f"{safe_name}.mp3"
                    # Rate -5% gives a calm, clear, articulate cadence
                    communicate = edge_tts.Communicate(text, self.FEMALE_VOICE, rate="-5%", pitch="+1Hz")
                    await communicate.save(str(file_path))

            loop.run_until_complete(generate_clips())
            loop.close()
        except Exception as e:
            print(f"Precache Audio Notice: {e}")

    def speak_mode(self, mode_name: str):
        """Instantly plays the high-quality cached neural female voice for search mode activation."""
        safe_name = mode_name.replace(" ", "_").replace("(", "").replace(")", "").lower()
        file_path = self.cache_dir / f"{safe_name}.mp3"

        if file_path.exists() and file_path.stat().st_size > 0:
            threading.Thread(target=self._play_cached_file, args=(str(file_path),), daemon=True).start()
        else:
            line = self.MODE_LINES.get(mode_name, "Mode activated.")
            self.speak(line)

    def _play_cached_file(self, file_path: str):
        try:
            self.stop_speaking()
            self._tts_speaking = True
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not self._stop_tts_event.is_set():
                time.sleep(0.05)
        except Exception as e:
            print(f"Play Cached Notice: {e}")
        finally:
            self._tts_speaking = False

    def _tts_loop(self):
        """Dedicated background synthesis and playback queue worker."""
        while True:
            item = self._tts_queue.get()
            if item is None:
                break

            text, callback_done = item

            if text and text.strip():
                try:
                    self._tts_speaking = True
                    self._stop_tts_event.clear()

                    cleaned = self._clean_for_speech(text)
                    if cleaned:
                        success = self._speak_edge_tts(cleaned)
                        if not success:
                            self._speak_sapi_fallback(cleaned)
                except Exception as e:
                    print(f"TTS Speech Error: {e}")
                finally:
                    self._tts_speaking = False
                    if callback_done:
                        try:
                            callback_done()
                        except Exception:
                            pass
            self._tts_queue.task_done()

    def _speak_edge_tts(self, text: str) -> bool:
        """Synthesizes speech using Microsoft Neural Edge TTS."""
        try:
            import edge_tts
            temp_file = self.cache_dir / f"response_{int(time.time() * 1000)}.mp3"

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def run_synth():
                speech_text = text if len(text) < 1500 else text[:1500] + "... and more."
                communicate = edge_tts.Communicate(speech_text, self.FEMALE_VOICE, rate="-3%")
                await communicate.save(str(temp_file))

            loop.run_until_complete(run_synth())
            loop.close()

            if temp_file.exists() and temp_file.stat().st_size > 0:
                pygame.mixer.music.load(str(temp_file))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and not self._stop_tts_event.is_set():
                    time.sleep(0.05)
                try:
                    pygame.mixer.music.unload()
                    os.remove(str(temp_file))
                except Exception:
                    pass
                return True
            return False
        except Exception as e:
            return False

    def _speak_sapi_fallback(self, text: str):
        """Offline fallback using pyttsx3 Zira."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('rate', 160)
            voices = engine.getProperty('voices')
            for v in voices:
                if 'zira' in v.name.lower() or 'female' in v.name.lower():
                    engine.setProperty('voice', v.id)
                    break
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"SAPI Fallback Notice: {e}")

    def _clean_for_speech(self, text: str) -> str:
        """Strips code blocks, markdown symbols, and URLs."""
        text = re.sub(r'```[\s\S]*?```', 'code block omitted', text)
        text = re.sub(r'[*#_`~>•\-]', ' ', text)
        text = re.sub(r'http\S+', '', text)
        return " ".join(text.split()).strip()

    # ==========================
    # PUBLIC TTS API
    # ==========================
    def speak(self, text: str, callback_done: Optional[Callable] = None):
        """Enqueues text for natural female voice narration."""
        self.stop_speaking()
        if text and text.strip():
            self._tts_queue.put((text, callback_done))

    def stop_speaking(self):
        """Immediately stops audio playback."""
        self._stop_tts_event.set()
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
                self._tts_queue.task_done()
            except queue.Empty:
                break

    @property
    def is_speaking(self) -> bool:
        return self._tts_speaking

    # ==========================
    # SPEECH TO TEXT (STT) API
    # ==========================
    def start_listening(self,
                        on_status: Callable[[str], None],
                        on_result: Callable[[str], None],
                        on_error: Callable[[str], None]):
        if self.is_listening:
            return

        self.stop_speaking()
        self.play_mic_on()
        self.is_listening = True
        self._stt_thread = threading.Thread(
            target=self._stt_worker,
            args=(on_status, on_result, on_error),
            daemon=True
        )
        self._stt_thread.start()

    def stop_listening(self):
        if self.is_listening:
            self.is_listening = False
            self.play_mic_off()

    def _stt_worker(self, on_status, on_result, on_error):
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                on_status("🎙️ Listening... Speak now.")
                recognizer.adjust_for_ambient_noise(source, duration=0.3)

                if not self.is_listening:
                    return

                audio = recognizer.listen(source, timeout=6, phrase_time_limit=18)
        except sr.WaitTimeoutError:
            if self.is_listening:
                self.play_mic_off()
                on_error("Voice timeout: No speech detected.")
            self.is_listening = False
            return
        except Exception as e:
            if self.is_listening:
                self.play_mic_off()
            on_error(f"Microphone error: {e}")
            self.is_listening = False
            return

        if not self.is_listening:
            return

        # Play stop chime to indicate listening has finished
        self.play_mic_off()

        try:
            on_status("⏳ Transcribing audio...")
            text = recognizer.recognize_google(audio)
            if text and text.strip():
                on_result(text.strip())
            else:
                on_error("No speech detected.")
        except sr.UnknownValueError:
            on_error("Could not understand the audio.")
        except Exception as e:
            on_error(f"Transcription error: {e}")
        finally:
            self.is_listening = False
