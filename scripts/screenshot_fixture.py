"""Dev-only script to serve the frontend with the sample fixture and capture Playwright screenshots."""

from __future__ import annotations

import argparse
import functools
import http.server
import io
import json
import socketserver
import threading
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "sample_result.json"
OUT_DIR = ROOT / "tmp" / "screenshots"

WIDTHS = [360, 390, 768, 1280, 1920]


def make_silent_wav(duration_sec: float, sample_rate: int = 8000) -> bytes:
    """Create a tiny silent mono 16-bit PCM WAV buffer for browser <audio> playback."""
    buf = io.BytesIO()
    n_frames = max(1, int(duration_sec * sample_rate))
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


class FixtureHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, fixture_bytes: bytes, wav_bytes: bytes, **kwargs):
        self.fixture_bytes = fixture_bytes
        self.wav_bytes = wav_bytes
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):
        if self.path.startswith("/fixture/sample_result.json"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(self.fixture_bytes)))
            self.end_headers()
            self.wfile.write(self.fixture_bytes)
            return
        if self.path.startswith("/fixture/silence.wav"):
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(self.wav_bytes)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(self.wav_bytes)
            return
        if self.path == "/api/health":
            payload = b'{"status":"ok","version":"0.1.0"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def log_message(self, format, *args):
        pass


def start_server():
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    fixture_data = json.loads(fixture_text)
    wav_bytes = make_silent_wav(float(fixture_data.get("duration", 98.0)))
    handler = functools.partial(
        FixtureHandler,
        fixture_bytes=fixture_text.encode("utf-8"),
        wav_bytes=wav_bytes,
    )
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, fixture_data


def capture_all(all_views: bool = False) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    server, port, fixture_data = start_server()
    base_url = f"http://127.0.0.1:{port}"
    beats = fixture_data["beat_chords"]

    # State timestamps:
    # paused: beat 0 (F#m7b5 -> C#dim7)
    # mid: bar 11 beat 2 (Cmaj7/G -> D/F#)
    # long: bar 2 beat 0 (held Ebmaj7)
    states = [
        ("paused", beats[0]["start"]),
        ("mid", beats[10 * 4 + 2]["start"]),
        ("long", beats[4]["start"]),
    ]

    saved: list[Path] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for width in WIDTHS:
                height = 800 if width < 768 else 900
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page.goto(base_url, wait_until="networkidle")

                if all_views:
                    start_path = OUT_DIR / f"start_{width}.png"
                    page.screenshot(path=str(start_path))
                    saved.append(start_path)

                page.evaluate(
                    """async () => {
                        const res = await fetch('/fixture/sample_result.json');
                        const data = await res.json();
                        renderAnalysis(data);
                        await new Promise((resolve) => {
                            const audio = document.getElementById('audio-player');
                            if (audio.readyState >= 1) return resolve();
                            audio.addEventListener('loadedmetadata', resolve, { once: true });
                            setTimeout(resolve, 1000);
                        });
                    }"""
                )
                page.wait_for_timeout(150)

                for state_name, target_time in states:
                    page.evaluate(
                        """(t) => {
                            const audio = document.getElementById('audio-player');
                            audio.currentTime = t;
                            if (typeof updatePlayhead === 'function') updatePlayhead();
                        }""",
                        target_time,
                    )
                    page.wait_for_timeout(120)
                    out_path = OUT_DIR / f"{state_name}_{width}.png"
                    page.screenshot(path=str(out_path))
                    saved.append(out_path)

                if all_views and width in (390, 1280):
                    page.click("#settings-btn")
                    page.wait_for_timeout(200)
                    settings_path = OUT_DIR / f"settings_{width}.png"
                    page.screenshot(path=str(settings_path))
                    saved.append(settings_path)
                    page.click("#settings-close-btn")
                    page.wait_for_timeout(150)

                context.close()
            browser.close()
    finally:
        server.shutdown()

    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-views", action="store_true", help="Also capture start screen and settings drawer")
    args = parser.parse_args()
    paths = capture_all(all_views=args.all_views)
    print(f"Captured {len(paths)} screenshots in {OUT_DIR}")


if __name__ == "__main__":
    main()

