# Third-Party Bundled Components and Licenses

ChordLens bundles several third-party binaries and pre-trained model weights to operate completely self-contained on Windows without requiring external runtime dependencies or internet downloads.

---

## 1. FFmpeg & FFprobe (LGPL v2.1+)

- **Component:** `bin/ffmpeg.exe`, `bin/ffprobe.exe`
- **Origin / Source:** Built by [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) from the official FFmpeg source code ([ffmpeg.org](https://ffmpeg.org)).
- **Build Variant:** Windows x86_64 LGPL shared/static build (`ffmpeg-master-latest-win64-lgpl.zip`).
- **License:** GNU Lesser General Public License (LGPL) version 2.1 or later.
- **Verification:** Verified via `ffmpeg -version` that the build does NOT contain `--enable-gpl` or `--enable-nonfree`.
- **LGPL Compliance:**
  - FFmpeg is invoked exclusively as an external subprocess via command-line arguments.
  - Users may replace `ffmpeg.exe` and `ffprobe.exe` in the application directory with any compatible build.
  - Source code for FFmpeg is available at https://ffmpeg.org and https://github.com/BtbN/FFmpeg-Builds.

---

## 2. Deno JavaScript Runtime (MIT)

- **Component:** `bin/deno.exe`
- **Origin / Source:** [Deno Land Releases](https://github.com/denoland/deno/releases) (`deno-x86_64-pc-windows-msvc.zip`).
- **Role:** Bundled JavaScript runtime used by `yt-dlp` for YouTube extraction and challenges.
- **License:** MIT License.

```text
Copyright 2018-2026 the Deno authors. All rights reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

---

## 3. beat_this Beat & Downbeat Tracking Model (MIT)

- **Component:** `models/beat_this/final0.ckpt`
- **Origin / Source:** CPJKU / Johannes Kepler University Linz ([CPJKU/beat_this](https://github.com/CPJKU/beat_this)).
- **Role:** Transformer-based beat and downbeat tracking model for Phase 2 rhythm analysis.
- **License:** MIT License.

```text
MIT License

Copyright (c) 2024 CPJKU

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 4. BTC Chord Recognition Model (MIT)

- **Component:** `models/btc-chord/btc_model_large_voca.pt`
- **Origin / Source:** puar-playground ([puar-playground/btc-chord](https://github.com/puar-playground/btc-chord)).
- **Role:** Bi-directional Transformer for Chord recognition (BTC large vocabulary model).
- **License:** MIT License.

```text
MIT License

Copyright (c) 2020 puar-playground

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

