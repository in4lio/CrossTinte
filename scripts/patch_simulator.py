from pathlib import Path

Import("env")  # noqa: F821 - SCons injects this at build time


def replace_once(path: Path, old: str, new: str, warn: bool = True) -> bool:
    text = path.read_text()
    if new in text:
        return False
    if old not in text:
        if warn:
            print(f"patch_simulator: expected text not found in {path}")
        return False
    path.write_text(text.replace(old, new, 1))
    return True


def patch_simulator(*_args, **_kwargs):
    libdeps_dir = Path(env.subst("$PROJECT_LIBDEPS_DIR"))
    pioenv = env.subst("$PIOENV")
    simulator_src = libdeps_dir / pioenv / "simulator" / "src"

    if not simulator_src.exists():
        print(f"patch_simulator: simulator dependency not found yet for {pioenv}")
        return

    changed = False

    hal_gpio = simulator_src / "HalGPIO.h"
    if hal_gpio.exists():
        changed |= replace_once(
            hal_gpio,
            "  DeviceType _deviceType = DeviceType::X4;",
            """#ifdef SIMULATOR_DEVICE_X3
  DeviceType _deviceType = DeviceType::X3;
#else
  DeviceType _deviceType = DeviceType::X4;
#endif""",
        )

    eink_display = simulator_src / "EInkDisplay.h"
    if eink_display.exists():
        changed |= replace_once(
            eink_display,
            """  static constexpr uint16_t DISPLAY_WIDTH = 800;
  static constexpr uint16_t DISPLAY_HEIGHT = 480;""",
            """#ifdef SIMULATOR_DEVICE_X3
  static constexpr uint16_t DISPLAY_WIDTH = 792;
  static constexpr uint16_t DISPLAY_HEIGHT = 528;
#else
  static constexpr uint16_t DISPLAY_WIDTH = 800;
  static constexpr uint16_t DISPLAY_HEIGHT = 480;
#endif""",
        )

    hal_display = simulator_src / "HalDisplay.cpp"
    if hal_display.exists():
        changed |= replace_once(
            hal_display,
            '  window = SDL_CreateWindow("Simulator - Open-X4 SDK", SDL_WINDOWPOS_UNDEFINED,',
            """#ifdef SIMULATOR_DEVICE_X3
  const char *windowTitle = "CrossInk Simulator - X3";
#else
  const char *windowTitle = "CrossInk Simulator - X4";
#endif
  window = SDL_CreateWindow(windowTitle, SDL_WINDOWPOS_UNDEFINED,""",
        )
        changed |= replace_once(
            hal_display,
            """static uint32_t
    pixelBuf[HalDisplay::DISPLAY_WIDTH * HalDisplay::DISPLAY_HEIGHT];
static std::atomic<bool> pendingPresent{false};""",
            """static uint32_t
    pixelBuf[HalDisplay::DISPLAY_WIDTH * HalDisplay::DISPLAY_HEIGHT];
static uint8_t displayedBwBuffer[HalDisplay::BUFFER_SIZE];
static uint8_t grayscaleLsbBuffer[HalDisplay::BUFFER_SIZE];
static uint8_t grayscaleMsbBuffer[HalDisplay::BUFFER_SIZE];
static bool displayedBwValid = false;
static bool grayscaleLsbValid = false;
static bool grayscaleMsbValid = false;
static std::atomic<bool> pendingPresent{false};""",
            warn=False,
        )
        changed |= replace_once(
            hal_display,
            """static uint32_t
    pixelBuf[HalDisplay::DISPLAY_WIDTH * HalDisplay::DISPLAY_HEIGHT];
static uint8_t grayscaleLsbBuffer[HalDisplay::BUFFER_SIZE];
static uint8_t grayscaleMsbBuffer[HalDisplay::BUFFER_SIZE];
static bool grayscaleLsbValid = false;
static bool grayscaleMsbValid = false;
static std::atomic<bool> pendingPresent{false};""",
            """static uint32_t
    pixelBuf[HalDisplay::DISPLAY_WIDTH * HalDisplay::DISPLAY_HEIGHT];
static uint8_t displayedBwBuffer[HalDisplay::BUFFER_SIZE];
static uint8_t grayscaleLsbBuffer[HalDisplay::BUFFER_SIZE];
static uint8_t grayscaleMsbBuffer[HalDisplay::BUFFER_SIZE];
static bool displayedBwValid = false;
static bool grayscaleLsbValid = false;
static bool grayscaleMsbValid = false;
static std::atomic<bool> pendingPresent{false};""",
            warn=False,
        )
        changed |= replace_once(
            hal_display,
            """void HalDisplay::refreshDisplay(RefreshMode /*mode*/, bool /*turnOffScreen*/) {
  const uint8_t *fb = getFrameBuffer();
  for (int y = 0; y < DISPLAY_HEIGHT; y++) {""",
            """void HalDisplay::refreshDisplay(RefreshMode /*mode*/, bool /*turnOffScreen*/) {
  const uint8_t *fb = getFrameBuffer();
  memcpy(displayedBwBuffer, fb, BUFFER_SIZE);
  displayedBwValid = true;
  for (int y = 0; y < DISPLAY_HEIGHT; y++) {""",
            warn=False,
        )
        changed |= replace_once(
            hal_display,
            """bool HalDisplay::shouldQuit() const { return quitRequested.load(); }

void HalDisplay::deepSleep() {}""",
            """bool HalDisplay::shouldQuit() const { return quitRequested.load(); }

static bool framebufferBitIsWhite(const uint8_t *fb, int x, int y) {
  const int byteIdx = (y * HalDisplay::DISPLAY_WIDTH + x) / 8;
  const int bitIdx = 7 - (x % 8);
  return (fb[byteIdx] & (1 << bitIdx)) != 0;
}

void HalDisplay::deepSleep() { presentIfNeeded(); }""",
            warn=False,
        )
        changed |= replace_once(
            hal_display,
            """void HalDisplay::deepSleep() {}""",
            """void HalDisplay::deepSleep() { presentIfNeeded(); }""",
            warn=False,
        )
        changed |= replace_once(
            hal_display,
            """void HalDisplay::copyGrayscaleBuffers(const uint8_t *, const uint8_t *) {}
void HalDisplay::copyGrayscaleLsbBuffers(const uint8_t *) {}
void HalDisplay::copyGrayscaleMsbBuffers(const uint8_t *) {}
void HalDisplay::cleanupGrayscaleBuffers(const uint8_t *) {}
void HalDisplay::displayGrayBuffer(bool, const unsigned char *, bool) {}""",
            """void HalDisplay::copyGrayscaleBuffers(const uint8_t *lsbBuffer, const uint8_t *msbBuffer) {
  if (lsbBuffer) {
    memcpy(grayscaleLsbBuffer, lsbBuffer, BUFFER_SIZE);
    grayscaleLsbValid = true;
  }
  if (msbBuffer) {
    memcpy(grayscaleMsbBuffer, msbBuffer, BUFFER_SIZE);
    grayscaleMsbValid = true;
  }
}

void HalDisplay::copyGrayscaleLsbBuffers(const uint8_t *lsbBuffer) {
  if (!lsbBuffer) return;
  memcpy(grayscaleLsbBuffer, lsbBuffer, BUFFER_SIZE);
  grayscaleLsbValid = true;
}

void HalDisplay::copyGrayscaleMsbBuffers(const uint8_t *msbBuffer) {
  if (!msbBuffer) return;
  memcpy(grayscaleMsbBuffer, msbBuffer, BUFFER_SIZE);
  grayscaleMsbValid = true;
}

void HalDisplay::cleanupGrayscaleBuffers(const uint8_t *) {
  grayscaleLsbValid = false;
  grayscaleMsbValid = false;
}

void HalDisplay::displayGrayBuffer(bool, const unsigned char *, bool) {
  const uint8_t *bw = displayedBwValid ? displayedBwBuffer : getFrameBuffer();
  for (int y = 0; y < DISPLAY_HEIGHT; y++) {
    for (int x = 0; x < DISPLAY_WIDTH; x++) {
      const bool bwWhite = framebufferBitIsWhite(bw, x, y);
      const bool lsb = grayscaleLsbValid && framebufferBitIsWhite(grayscaleLsbBuffer, x, y);
      const bool msb = grayscaleMsbValid && framebufferBitIsWhite(grayscaleMsbBuffer, x, y);

      uint32_t color = 0xFFFFFFFF;
      if (!bwWhite) {
        if (msb && lsb) {
          color = 0xFF555555;
        } else if (msb) {
          color = 0xFFAAAAAA;
        } else {
          color = 0xFF000000;
        }
      }
      pixelBuf[y * DISPLAY_WIDTH + x] = color;
    }
  }
  pendingPresent.store(true);
}""",
            warn=False,
        )
        changed |= replace_once(
            hal_display,
            """void HalDisplay::displayGrayBuffer(bool, const unsigned char *, bool) {
  const uint8_t *bw = getFrameBuffer();
  for (int y = 0; y < DISPLAY_HEIGHT; y++) {
    for (int x = 0; x < DISPLAY_WIDTH; x++) {
      const bool bwWhite = framebufferBitIsWhite(bw, x, y);
      const bool lsb = grayscaleLsbValid && framebufferBitIsWhite(grayscaleLsbBuffer, x, y);
      const bool msb = grayscaleMsbValid && framebufferBitIsWhite(grayscaleMsbBuffer, x, y);

      uint32_t color = 0xFFFFFFFF;
      if (!bwWhite) {
        if (msb && lsb) {
          color = 0xFF555555;
        } else if (msb) {
          color = 0xFFAAAAAA;
        } else {
          color = 0xFF000000;
        }
      }
      pixelBuf[y * DISPLAY_WIDTH + x] = color;
    }
  }
  pendingPresent.store(true);
}""",
            """void HalDisplay::displayGrayBuffer(bool, const unsigned char *, bool) {
  const uint8_t *bw = displayedBwValid ? displayedBwBuffer : getFrameBuffer();
  for (int y = 0; y < DISPLAY_HEIGHT; y++) {
    for (int x = 0; x < DISPLAY_WIDTH; x++) {
      const bool bwWhite = framebufferBitIsWhite(bw, x, y);
      const bool lsb = grayscaleLsbValid && framebufferBitIsWhite(grayscaleLsbBuffer, x, y);
      const bool msb = grayscaleMsbValid && framebufferBitIsWhite(grayscaleMsbBuffer, x, y);

      uint32_t color = 0xFFFFFFFF;
      if (!bwWhite) {
        if (msb && lsb) {
          color = 0xFF555555;
        } else if (msb) {
          color = 0xFFAAAAAA;
        } else {
          color = 0xFF000000;
        }
      }
      pixelBuf[y * DISPLAY_WIDTH + x] = color;
    }
  }
  pendingPresent.store(true);
}""",
            warn=False,
        )

    if changed:
        print(f"patch_simulator: patched simulator dependency for {pioenv}")

    wifi_h = simulator_src / "WiFi.h"
    if wifi_h.exists():
        wifi_text = wifi_h.read_text()
        changed_wifi = False
        if "setAutoReconnect" not in wifi_text:
            changed_wifi = replace_once(
                wifi_h,
                "  void setAutoConnect(bool b);",
                """  void setAutoConnect(bool b);
  void setAutoReconnect(bool b);""",
            )
        if changed_wifi:
            print(f"patch_simulator: patched WiFi API for {pioenv}")

    wifi_cpp = simulator_src / "WiFi.cpp"
    if wifi_cpp.exists():
        wifi_text = wifi_cpp.read_text()
        changed_wifi = False
        if "setAutoReconnect" not in wifi_text:
            changed_wifi = replace_once(
                wifi_cpp,
                "void WiFiClass::setAutoConnect(bool b) {}",
                """void WiFiClass::setAutoConnect(bool b) {}
void WiFiClass::setAutoReconnect(bool b) {}""",
            )
        if changed_wifi:
            print(f"patch_simulator: patched WiFi implementation for {pioenv}")

    pngdec = simulator_src / "PNGdec.h"
    if pngdec.exists():
        pngdec_forwarder = """#pragma once
// CrossPoint patch: use the real PNGdec library in simulator builds.
// The simulator dependency ships a stub that always fails decode(); forwarding
// to the PlatformIO PNGdec dependency keeps Page Overlay PNG behavior testable.
#include "../../PNGdec/src/PNGdec.h"
"""
        text = pngdec.read_text()
        if "../../PNGdec/src/PNGdec.h" not in text:
            pngdec.write_text(pngdec_forwarder)
            print(f"patch_simulator: forwarded PNGdec stub for {pioenv}")

    pngdec_src = libdeps_dir / pioenv / "PNGdec" / "src"
    if pngdec_src.exists():
        env.Append(CPPPATH=[str(pngdec_src)])
        env.BuildSources(
            "$BUILD_DIR/libpngdec_real",
            str(pngdec_src),
            ["+<*.c>", "+<*.cpp>", "-<s3_simd_rgb565.S>"],
        )

    jpegdec = simulator_src / "JPEGDEC.h"
    if jpegdec.exists():
        jpegdec_forwarder = """#pragma once
// CrossPoint patch: use the real JPEGDEC library in simulator builds.
// The simulator dependency ships a stub that always fails open(); forwarding
// to the PlatformIO JPEGDEC dependency keeps EPUB cover generation testable.
#include "../../JPEGDEC/src/JPEGDEC.h"
"""
        text = jpegdec.read_text()
        if "../../JPEGDEC/src/JPEGDEC.h" not in text:
            jpegdec.write_text(jpegdec_forwarder)
            print(f"patch_simulator: forwarded JPEGDEC stub for {pioenv}")

    jpegdec_src = libdeps_dir / pioenv / "JPEGDEC" / "src"
    if jpegdec_src.exists():
        env.Append(CPPPATH=[str(jpegdec_src)])
        env.BuildSources(
            "$BUILD_DIR/libjpegdec_real",
            str(jpegdec_src),
            ["+<*.c>", "+<*.cpp>", "-<*.S>"],
        )


patch_simulator()
env.AddPreAction("buildprog", patch_simulator)
