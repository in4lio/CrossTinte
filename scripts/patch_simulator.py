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
    hal_display = libdeps_dir / pioenv / "simulator" / "src" / "HalDisplay.cpp"

    if not hal_display.exists():
        print(f"patch_simulator: simulator dependency not found yet for {pioenv}")
        return

    text = hal_display.read_text()
    if "displayedBwBuffer" in text and "displayGrayBuffer(bool, const unsigned char *, bool) {}" not in text:
        return

    changed = False
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
    )
    changed |= replace_once(
        hal_display,
        """bool HalDisplay::shouldQuit() const { return quitRequested.load(); }

void HalDisplay::deepSleep() { presentIfNeeded(); }""",
        """bool HalDisplay::shouldQuit() const { return quitRequested.load(); }

static bool framebufferBitIsWhite(const uint8_t *fb, int x, int y) {
  const int byteIdx = (y * HalDisplay::DISPLAY_WIDTH + x) / 8;
  const int bitIdx = 7 - (x % 8);
  return (fb[byteIdx] & (1 << bitIdx)) != 0;
}

void HalDisplay::deepSleep() { presentIfNeeded(); }""",
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
    )

    if changed:
        print(f"patch_simulator: patched grayscale display support for {pioenv}")


patch_simulator()
env.AddPreAction("buildprog", patch_simulator)
