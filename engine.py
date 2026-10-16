"""GravaTrem — motor de captura e gravacao.

Extraido da antiga ``app_tk_legado.py`` (interface tkinter descontinuada).
Este modulo NAO tem dependencia de tkinter nem de Qt: apenas captura
(mss), audio (sounddevice / pyaudiowpatch), DSP (numpy) e mux (PyAV).

Responsabilidades:
    - config/i18n: ``load_lang``, ``default_output_folder``
    - audio: ``_find_loopback``, ``_resample_mono``, ``LiveMonitor``
    - video: ``get_cursor_pos``, ``draw_cursor``
    - gravacao: ``record_screen`` (tela + mic e/ou sistema -> MP4 H.264 + AAC)
    - medicao: ``new_meter``, ``_feed_meter``, ``_db``
"""

import configparser
import os
import queue
import shutil
import sys
import threading
import time
from collections import deque
from pathlib import Path

import av
import mss
import numpy as np
import sounddevice as sd

try:
    import pyaudiowpatch as pyaudio
    HAS_LOOPBACK = True
except ImportError:  # sem loopback: so microfone / so video
    pyaudio = None
    HAS_LOOPBACK = False


def _is_frozen():
    return bool(getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"))


BASE_DIR = Path(__file__).resolve().parent
# No bundle congelado (PyInstaller onedir) os dados ficam em sys._MEIPASS
# (= dist/GravaTrem/_internal); em dev continuam ao lado do fonte.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", str(BASE_DIR)))
LANG_DIR = BUNDLE_DIR / "lang"
BUNDLED_INI = BUNDLE_DIR / "app.ini"


def user_config_path():
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    return base / "GravaTrem" / "app.ini"


def _resolve_app_ini():
    """Em dev: app.ini ao lado do fonte. Congelado: %APPDATA%/GravaTrem/app.ini
    (Program Files nao e gravavel com PrivilegesRequired=lowest). Semeia o
    arquivo do usuario a partir do default embutido no bundle, se houver."""
    if not _is_frozen():
        return BASE_DIR / "app.ini"
    target = user_config_path()
    try:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if BUNDLED_INI.exists():
                shutil.copyfile(BUNDLED_INI, target)
    except OSError:
        pass
    return target


APP_INI = _resolve_app_ini()

DEFAULTS = {
    "soutputfolder": "",
    "slangfile": "Portuguese(BR).ini",
    "dwfps": "15",
    "dwsamplerate": "44100",
    "saudiomode": "both",
    "spresetlabel": "Equilibrado",
    "scapmode": "full",
    "dwmonitor": "1",
    "sregion": "",
    "sshowcursor": "1",
}


def resource_path(name):
    """Caminho de um recurso embutido (icon.ico, lang/...) funcionando em
    dev e no bundle congelado."""
    return BUNDLE_DIR / name


def ensure_defaults(cfg):
    """Garante secao OPTION + defaults mesmo com app.ini ausente/incompleto.
    Sem isso, cfg.set('OPTION', ...) levanta NoSectionError no instalado."""
    if not cfg.has_section("OPTION"):
        cfg.add_section("OPTION")
    for k, v in DEFAULTS.items():
        if not cfg.has_option("OPTION", k):
            cfg.set("OPTION", k, v)
    return cfg


def save_config(cfg):
    """Persiste cfg no local gravavel (resolve APP_INI de novo por seguranca)."""
    ensure_defaults(cfg)
    target = _resolve_app_ini()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8-sig") as f:
            cfg.write(f)
    except OSError:
        # ex.: perfil sem APPDATA gravavel — nao derruba a gravacao por causa disso
        pass
    return target

__all__ = [
    "APP_INI", "BASE_DIR", "BUNDLE_DIR", "BUNDLED_INI", "HAS_LOOPBACK", "LANG_DIR",
    "LiveMonitor", "default_output_folder", "draw_cursor", "ensure_defaults",
    "get_cursor_pos", "load_lang", "new_meter", "record_screen", "resource_path",
    "save_config", "user_config_path",
]


def load_lang():
    cfg = configparser.ConfigParser()
    try:
        if APP_INI.exists():
            cfg.read(APP_INI, encoding="utf-8-sig")
        elif BUNDLED_INI.exists() and BUNDLED_INI != APP_INI:
            cfg.read(BUNDLED_INI, encoding="utf-8-sig")
    except OSError:
        pass
    ensure_defaults(cfg)
    lang = configparser.ConfigParser()
    lang.read(LANG_DIR / cfg.get("OPTION", "sLangFile", fallback="Portuguese(BR).ini"),
              encoding="utf-8-sig")
    if not lang.has_section("TEXT"):
        lang.read(LANG_DIR / "English.ini", encoding="utf-8-sig")
    return cfg, dict(lang["TEXT"])


def default_output_folder(cfg):
    folder = cfg.get("OPTION", "sOutputFolder", fallback="").strip()
    if folder:
        return Path(folder)
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "GravaTrem"


def _find_loopback():
    """Retorna (index, rate, name) do loopback do dispositivo de saida padrao, ou None."""
    if not HAS_LOOPBACK:
        return None
    pa = pyaudio.PyAudio()
    try:
        out_name = pa.get_device_info_by_index(pa.get_default_output_device_info()["index"])["name"]
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if d.get("isLoopbackDevice") and out_name in d["name"]:
                return (i, int(d["defaultSampleRate"]), d["name"])
    finally:
        pa.terminate()
    return None


def _resample_mono(x, src_rate, dst_rate):
    x = np.asarray(x, dtype=np.float32)
    if src_rate == dst_rate or x.size == 0:
        return x
    n_out = int(round(x.size * dst_rate / src_rate))
    return np.interp(np.linspace(0, x.size - 1, n_out), np.arange(x.size), x).astype(np.float32)


def get_cursor_pos():
    try:
        import win32gui
        return win32gui.GetCursorPos()
    except Exception:
        return None


def draw_cursor(rgb, cx, cy):
    """Desenha seta do mouse no frame (RGB ou BGRA) via numpy (mss nao captura o cursor)."""
    h, w, ch = rgb.shape
    spr, alpha = _cursor_sprite()
    sh, sw, _ = spr.shape
    sx0, sy0 = max(0, -int(cx)), max(0, -int(cy))
    x0c, y0c = max(0, int(cx)), max(0, int(cy))
    x1c, y1c = min(w, int(cx) + sw), min(h, int(cy) + sh)
    if x1c <= x0c or y1c <= y0c:
        return rgb
    tgt = rgb[y0c:y1c, x0c:x1c].astype(np.float32)
    a = (alpha[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c), None].astype(np.float32)) / 255.0
    s = spr[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)].astype(np.float32)
    if ch == 4:
        tgt[..., :3] = tgt[..., :3] * (1.0 - a) + s * a
    else:
        tgt = tgt * (1.0 - a) + s * a
    rgb[y0c:y1c, x0c:x1c] = tgt.astype(np.uint8)
    return rgb


_SPRITE = None


def _cursor_sprite():
    global _SPRITE
    if _SPRITE is None:
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (18, 25), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pts = [(1, 1), (1, 15), (5, 11), (7, 16), (9, 15), (7, 10), (12, 10)]
        d.polygon(pts, fill=(255, 255, 255, 255))
        d.line(pts + [pts[0]], fill=(0, 0, 0, 255), width=1)
        a = np.asarray(im)
        _SPRITE = (a[..., :3].copy(), a[..., 3].copy())
    return _SPRITE


def _feed_meter(meter, key, chunk):
    peak = float(np.max(np.abs(chunk))) if chunk.size else 0.0
    meter[key] = (peak, time.time())
    try:
        meter["wave_" + key].append(peak)
    except (KeyError, AttributeError):
        pass


def new_meter():
    return {"mic": (0.0, 0.0), "sys": (0.0, 0.0),
            "wave_mic": deque(maxlen=240), "wave_sys": deque(maxlen=240)}


def _db(peak):
    if peak <= 0.0001:
        return "-inf dB"
    return f"{20.0 * np.log10(peak):+.0f} dB"


class LiveMonitor:
    """Mantem mic e/ou loopback abertos no idle para VU + grafico ao vivo."""

    def __init__(self, meter, samplerate=44100):
        self.meter = meter
        self.samplerate = samplerate
        self.mic_stream = None
        self.pa = None
        self.sys_stream = None
        self.running = False

    def start(self, mic_device_or_none, sys_on):
        self.stop()
        try:
            if mic_device_or_none is not None:
                def mic_cb(indata, frames, time_info, status):
                    _feed_meter(self.meter, "mic", indata[:, 0])

                self.mic_stream = sd.InputStream(device=mic_device_or_none, samplerate=self.samplerate,
                                                 channels=1, dtype="float32", callback=mic_cb)
                self.mic_stream.start()
            if sys_on:
                info = _find_loopback()
                if info is not None:
                    idx, rate, _ = info
                    self.pa = pyaudio.PyAudio()

                    def sys_cb(in_data, frame_count, time_info, status):
                        stereo = np.frombuffer(in_data, dtype=np.float32).reshape(-1, 2)
                        _feed_meter(self.meter, "sys", _resample_mono(stereo.mean(axis=1), rate, self.samplerate))
                        return (None, pyaudio.paContinue)

                    self.sys_stream = self.pa.open(format=pyaudio.paFloat32, channels=2, rate=rate,
                                                   frames_per_buffer=1024, input=True,
                                                   input_device_index=idx, stream_callback=sys_cb)
                    self.sys_stream.start_stream()
            self.running = True
        except Exception as exc:
            print("monitor error:", exc)
            self.stop()

    def stop(self):
        self.running = False
        if self.mic_stream is not None:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except Exception:
                pass
            self.mic_stream = None
        if self.sys_stream is not None:
            try:
                self.sys_stream.stop_stream()
                self.sys_stream.close()
            except Exception:
                pass
            self.sys_stream = None
        if self.pa is not None:
            try:
                self.pa.terminate()
            except Exception:
                pass
            self.pa = None


def record_screen(path, fps, samplerate, mic_device_or_none, sys_on, stop_event,
                  meter=None, status_cb=None, region=None, show_cursor=True, preset="veryfast"):
    """Grava tela (regiao ou monitor primario) + microfone e/ou audio do sistema."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mic_q = queue.Queue()
    sys_q = queue.Queue()
    t0 = time.time()
    last = {"mic": t0, "sys": t0}

    def mic_cb(indata, frames, time_info, status):
        mic_q.put((time.time(), indata[:, 0].copy()))  # mono + timestamp
        last["mic"] = time.time()
        if meter is not None:
            _feed_meter(meter, "mic", indata[:, 0])

    mic_stream = None
    if mic_device_or_none is not None:
        mic_stream = sd.InputStream(device=mic_device_or_none, samplerate=samplerate,
                                    channels=1, dtype="float32", callback=mic_cb)
        mic_stream.start()

    pa = None
    sys_stream = None
    sys_info = _find_loopback() if sys_on else None
    if sys_on and sys_info is not None:
        sys_idx, sys_rate, _ = sys_info
        pa = pyaudio.PyAudio()

        def sys_cb(in_data, frame_count, time_info, status):
            stereo = np.frombuffer(in_data, dtype=np.float32).reshape(-1, 2)
            mono = _resample_mono(stereo.mean(axis=1), sys_rate, samplerate)
            sys_q.put((time.time(), mono))
            last["sys"] = time.time()
            if meter is not None:
                _feed_meter(meter, "sys", mono)
            return (None, pyaudio.paContinue)

        sys_stream = pa.open(format=pyaudio.paFloat32, channels=2, rate=sys_rate,
                             frames_per_buffer=1024, input=True,
                             input_device_index=sys_idx, stream_callback=sys_cb)
        sys_stream.start_stream()
    elif sys_on:
        print("loopback nao encontrado; seguindo sem audio do sistema")

    t0 = time.time()
    last = {"mic": t0, "sys": t0}
    period = 1.0 / fps

    def safe_grab(mon):
        try:
            return sct.grab(mon)
        except Exception:
            return None

    try:
        with mss.MSS() as sct:
            if region is None:
                mon = sct.monitors[1]  # monitor primario
            else:
                mon = {"left": int(region["left"]), "top": int(region["top"]),
                       "width": int(region["width"]) // 2 * 2, "height": int(region["height"]) // 2 * 2}
            from fractions import Fraction
            w, h = mon["width"], mon["height"]
            container = av.open(str(path), "w")
            vstream = container.add_stream("libx264", rate=fps)
            vstream.width = w
            vstream.height = h
            vstream.pix_fmt = "yuv420p"
            vstream.time_base = Fraction(1, fps)
            vstream.options = {"preset": preset, "tune": "zerolatency"}
            astream = None
            if mic_stream is not None or sys_stream is not None:
                astream = container.add_stream("aac", rate=samplerate, layout="mono")
                astream.time_base = Fraction(1, samplerate)
            t_start = time.time()
            vpts = 0
            apts = None  # ancora no relogio na primeira janela de audio
            mic_buf = np.zeros(0, dtype=np.float32)
            sys_buf = np.zeros(0, dtype=np.float32)
            pend = np.zeros(0, dtype=np.float32)  # resto <1024 entre iteracoes
            nxt = time.time()
            while not stop_event.is_set():
                img = safe_grab(mon)
                if img is None:
                    time.sleep(0.02)
                    continue
                rgb = np.array(img)[..., :3][..., ::-1].copy()  # BGRA -> RGB
                if show_cursor:
                    pos = get_cursor_pos()
                    if pos:
                        rgb = draw_cursor(rgb, pos[0] - mon["left"], pos[1] - mon["top"])
                frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
                frame.pts = int((time.time() - t_start) * fps)  # relogio de parede: compensa frames lentos
                if frame.pts < vpts:
                    frame.pts = vpts
                vpts = frame.pts + 1
                for pkt in vstream.encode(frame):
                    container.mux(pkt)
                if astream is not None:
                    while True:
                        try:
                            _, c = mic_q.get_nowait()
                            mic_buf = np.concatenate([mic_buf, c])
                        except queue.Empty:
                            break
                    while True:
                        try:
                            _, c = sys_q.get_nowait()
                            sys_buf = np.concatenate([sys_buf, c])
                        except queue.Empty:
                            break
                    now = time.time()
                    # tolera lado travado: apos 0.5s sem dados, segue com o outro lado
                    mic_live = mic_stream is not None and (now - last["mic"] < 0.5 or mic_buf.size > 0)
                    sys_live = sys_stream is not None and (now - last["sys"] < 0.5 or sys_buf.size > 0)
                    if mic_stream is not None and sys_stream is not None and mic_live and sys_live:
                        n = min(mic_buf.size, sys_buf.size)
                        new, mic_buf, sys_buf = mic_buf[:n] + sys_buf[:n], mic_buf[n:], sys_buf[n:]
                    elif mic_live:
                        new, mic_buf = mic_buf, np.zeros(0, dtype=np.float32)
                    elif sys_live:
                        new, sys_buf = sys_buf, np.zeros(0, dtype=np.float32)
                    else:
                        new = np.zeros(0, dtype=np.float32)
                    pend = np.concatenate([pend, new]) if new.size else pend
                    while pend.size >= 1024:
                        chunk, pend = pend[:1024], pend[1024:]
                        if apts is None:  # ancora o inicio do audio no relogio de parede
                            apts = max(0, int((time.time() - t_start) * samplerate) - 1024)
                        af = av.AudioFrame.from_ndarray(np.clip(chunk, -1.0, 1.0).reshape(1, -1),
                                                        format="fltp", layout="mono")
                        af.sample_rate = samplerate
                        af.pts = apts
                        apts += 1024
                        for pkt in astream.encode(af):
                            container.mux(pkt)
                if status_cb:
                    status_cb()
                nxt += period
                time.sleep(max(0.0, nxt - time.time()))
            for pkt in vstream.encode(None):
                container.mux(pkt)
            if astream is not None:
                for pkt in astream.encode(None):
                    container.mux(pkt)
            container.close()
    finally:
        if mic_stream is not None:
            mic_stream.stop()
            mic_stream.close()
        if sys_stream is not None:
            sys_stream.stop_stream()
            sys_stream.close()
        if pa is not None:
            pa.terminate()
    return path
