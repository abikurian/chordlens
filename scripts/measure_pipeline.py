"""Measurement script for ChordLens baseline and optimized performance.
Measures with timestamps:
- App start (process start -> server ready -> window created -> UI usable)
- YouTube path stages (metadata/download, audio conversion, analysis stages, done)
- YouTube repeat (cache hit)
- File path stages (upload, decode, beat tracking, chord model, key/sections, done)
- File repeat (cache hit)
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXE_PATH = ROOT / "dist" / "ChordLens" / "ChordLens.exe"
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
LOG_PATH = Path(LOCALAPPDATA) / "ChordLens" / "logs" / "chordlens.log"
CACHE_DIR = ROOT / "cache"
CACHE_YT_DIR = ROOT / "cache" / "youtube"
YT_URL = "https://youtu.be/nPV9Fvo59L0"


def wait_for_port_and_window(proc, initial_log_offset, timeout_sec=30.0):
    t0 = time.time()
    port = None
    window_created_t = None
    server_ready_t = None

    while time.time() - t0 < timeout_sec:
        if proc.poll() is not None:
            raise RuntimeError(f"ChordLens.exe exited unexpectedly with code {proc.returncode}")

        if LOG_PATH.exists():
            try:
                with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(initial_log_offset)
                    new_lines = f.readlines()
                for line in new_lines:
                    if "starting uvicorn on port" in line and not port:
                        try:
                            port = int(line.split("port")[-1].strip())
                        except Exception:
                            pass
                    if "Server is ready on port" in line and not server_ready_t:
                        server_ready_t = time.time()
                    if "WebView window created" in line and not window_created_t:
                        window_created_t = time.time()
            except Exception:
                pass

        if port and server_ready_t:
            # Check /api/health
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as r:
                    if r.status == 200:
                        break
            except Exception:
                pass
        time.sleep(0.05)

    if not port:
        raise TimeoutError("Could not find server port from new logs within timeout")

    t_now = time.time()
    return port, (server_ready_t or t_now) - t0, (window_created_t or t_now) - t0


def poll_job(port, job_id, timeout_sec=120.0):
    t0 = time.time()
    url = f"http://127.0.0.1:{port}/api/jobs/{job_id}"
    stage_history = []
    current_stage = None

    while time.time() - t0 < timeout_sec:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2.0) as res:
            data = json.loads(res.read().decode("utf-8"))

        stage = data.get("stage") or data.get("status")
        now = time.time()
        if stage != current_stage:
            stage_history.append((now - t0, stage))
            current_stage = stage

        if data.get("status") == "done":
            return now - t0, stage_history, data.get("result")
        if data.get("status") == "error":
            raise RuntimeError(f"Job failed: {data.get('error')}")

        time.sleep(0.05)

    raise TimeoutError(f"Job {job_id} timed out after {timeout_sec}s")


def main():
    print("=" * 60)
    print("ChordLens Performance Measurement")
    print(f"Target Exe: {EXE_PATH}")
    print("=" * 60)

    if not EXE_PATH.is_file():
        print(f"ERROR: {EXE_PATH} does not exist!")
        sys.exit(1)

    initial_offset = LOG_PATH.stat().st_size if LOG_PATH.exists() else 0

    # 1. Measure Startup
    print("\n[Stage 1] Measuring App Launch...")
    t_start = time.time()
    proc = subprocess.Popen([str(EXE_PATH), "--test-close-after=300"])
    try:
        port, time_server_ready, time_window_created = wait_for_port_and_window(proc, initial_offset)
        print(f"  Detected port: {port}")
        # Check UI HTML load time
        t_ui0 = time.time()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5.0) as r:
            _ = r.read()
        time_ui_usable = (time.time() - t_ui0) + time_window_created
        print(f"  Process start -> Server ready:  {time_server_ready:.3f} s")
        print(f"  Process start -> Window visible: {time_window_created:.3f} s")
        print(f"  Process start -> UI usable:      {time_ui_usable:.3f} s")

        # 2. Measure YouTube Path (Fresh)
        print(f"\n[Stage 2] Measuring YouTube Path: {YT_URL}")
        from backend.youtube import normalize_youtube_url
        clean_yt = normalize_youtube_url(YT_URL)
        yt_hash = hashlib.sha256(clean_yt.encode("utf-8")).hexdigest()[:24]
        audio_id = f"yt{yt_hash}"
        meta_file = CACHE_YT_DIR / f"{audio_id}.json"
        wav_file = CACHE_YT_DIR / f"{audio_id}.wav"
        meta_file.unlink(missing_ok=True)
        wav_file.unlink(missing_ok=True)

        t_click = time.time()
        payload = json.dumps({"url": YT_URL, "mode": "fast"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/jobs/analyze-url",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10.0) as r:
            start_res = json.loads(r.read().decode("utf-8"))
        t_feedback = time.time() - t_click
        job_id = start_res["job_id"]
        print(f"  Click -> First visible feedback (job queued): {t_feedback:.3f} s")

        yt_total, yt_stages, yt_result = poll_job(port, job_id, timeout_sec=120.0)
        print(f"  YouTube total pipeline: {yt_total:.3f} s")
        for elapsed, stg in yt_stages:
            print(f"    + {elapsed:.2f}s: {stg}")

        # 3. Measure YouTube Cache Hit
        print(f"\n[Stage 3] Measuring YouTube Cache Hit (Repeat)...")
        t_click_repeat = time.time()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/jobs/analyze-url",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10.0) as r:
            repeat_res = json.loads(r.read().decode("utf-8"))
        yt_repeat_feedback = time.time() - t_click_repeat
        yt_repeat_total, _, _ = poll_job(port, repeat_res["job_id"], timeout_sec=30.0)
        print(f"  YouTube repeat total: {yt_repeat_total:.3f} s (feedback: {yt_repeat_feedback:.3f} s)")

        # 4. Measure File Path (using the downloaded real song)
        found_audio = None
        for cand in CACHE_YT_DIR.glob(f"{audio_id}.*"):
            if cand.suffix.lower() != ".json":
                found_audio = cand
                break

        if not found_audio or not found_audio.is_file():
            for cand in CACHE_YT_DIR.glob("*.wav"):
                found_audio = cand
                break

        if found_audio:
            print(f"\n[Stage 4] Measuring Local File Path on real song: {found_audio.name} ({found_audio.stat().st_size / 1024 / 1024:.2f} MB)...")
            file_bytes = found_audio.read_bytes()
            h = hashlib.sha256(file_bytes).hexdigest()
            cache_file = CACHE_DIR / f"{h}_fast_v3.json"
            cache_file.unlink(missing_ok=True)

            boundary = "----WebKitFormBoundaryChordLensBench"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{found_audio.name}"\r\n'
                f"Content-Type: audio/wav\r\n\r\n"
            ).encode("utf-8") + file_bytes + (
                f"\r\n--{boundary}\r\n"
                f'Content-Disposition: form-data; name="mode"\r\n\r\n'
                f"fast\r\n--{boundary}--\r\n"
            ).encode("utf-8")

            t_file_click = time.time()
            file_req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/jobs/analyze",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(file_req, timeout=20.0) as r:
                file_start_res = json.loads(r.read().decode("utf-8"))
            file_feedback = time.time() - t_file_click
            file_job_id = file_start_res["job_id"]
            print(f"  File upload click -> First feedback: {file_feedback:.3f} s")

            file_total, file_stages, file_result = poll_job(port, file_job_id, timeout_sec=120.0)
            print(f"  File analysis total: {file_total:.3f} s")
            for elapsed, stg in file_stages:
                print(f"    + {elapsed:.2f}s: {stg}")

            # 5. Measure File Cache Hit (Repeat)
            print(f"\n[Stage 5] Measuring Local File Cache Hit (Repeat)...")
            t_file_repeat_click = time.time()
            file_req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/jobs/analyze",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(file_req, timeout=20.0) as r:
                file_repeat_res = json.loads(r.read().decode("utf-8"))
            file_repeat_feedback = time.time() - t_file_repeat_click
            file_repeat_total, _, _ = poll_job(port, file_repeat_res["job_id"], timeout_sec=20.0)
            print(f"  File repeat total: {file_repeat_total:.3f} s (feedback: {file_repeat_feedback:.3f} s)")

    finally:
        print("\nStopping ChordLens.exe test process...")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        subprocess.run(["powershell", "-Command", "Get-Process ChordLens -ErrorAction SilentlyContinue | Stop-Process -Force"], check=False)
        print("Cleaned up.")


if __name__ == "__main__":
    main()
