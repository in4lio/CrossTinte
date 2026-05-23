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
    http_client = libdeps_dir / pioenv / "simulator" / "src" / "HTTPClient.h"
    network_client = libdeps_dir / pioenv / "simulator" / "src" / "NetworkClient.h"
    stream = libdeps_dir / pioenv / "simulator" / "src" / "Stream.h"

    if not hal_display.exists():
        print(f"patch_simulator: simulator dependency not found yet for {pioenv}")
        return

    text = hal_display.read_text()
    if "displayedBwBuffer" in text and "displayGrayBuffer(bool, const unsigned char *, bool) {}" not in text:
        pass

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

    http_changed = False
    if stream.exists():
        http_changed |= replace_once(
            stream,
            """  size_t readBytes(char *buffer, size_t length) { return 0; }""",
            """  virtual size_t readBytes(uint8_t *buffer, size_t length) {
    size_t count = 0;
    while (count < length && available() > 0) {
      const int c = read();
      if (c < 0) break;
      buffer[count++] = static_cast<uint8_t>(c);
    }
    return count;
  }
  virtual size_t readBytes(char *buffer, size_t length) {
    return readBytes(reinterpret_cast<uint8_t *>(buffer), length);
  }""",
            warn=False,
        )
        http_changed |= replace_once(
            stream,
            """  virtual size_t readBytes(char *buffer, size_t length) {
    size_t count = 0;
    while (count < length && available() > 0) {
      const int c = read();
      if (c < 0) break;
      buffer[count++] = static_cast<char>(c);
    }
    return count;
  }""",
            """  virtual size_t readBytes(uint8_t *buffer, size_t length) {
    size_t count = 0;
    while (count < length && available() > 0) {
      const int c = read();
      if (c < 0) break;
      buffer[count++] = static_cast<uint8_t>(c);
    }
    return count;
  }
  virtual size_t readBytes(char *buffer, size_t length) {
    return readBytes(reinterpret_cast<uint8_t *>(buffer), length);
  }""",
            warn=False,
        )

    if network_client.exists():
        http_changed |= replace_once(
            network_client,
            """class NetworkClientSecure : public NetworkClient {
public:
  void setInsecure() {}
};""",
            """class NetworkClientSecure : public NetworkClient {
public:
  void setInsecure() {}
  void setHandshakeTimeout(uint32_t) {}
};""",
        )

    if http_client.exists():
        http_changed |= replace_once(
            http_client,
            '''#include "SimHttpFetch.h"
#include "Stream.h"
#include "WString.h"''',
            '''#include "SimHttpFetch.h"
#include "Stream.h"
#include "StreamString.h"
#include "WString.h"''',
        )
        http_changed |= replace_once(
            http_client,
            """    responseBody_.s.clear();
    statusCode_ = 0;""",
            """    responseBody_.s.clear();
    responseStream_.clear();
    statusCode_ = 0;""",
        )
        http_changed |= replace_once(
            http_client,
            """  void setFollowRedirects(int mode) {}""",
            """  void setFollowRedirects(int mode) {}
  void setReuse(bool) {}
  void setConnectTimeout(int) {}
  void setTimeout(int) {}""",
        )
        http_changed |= replace_once(
            http_client,
            """  String getString() { return responseBody_; }
  int getSize() { return static_cast<int>(responseBody_.length()); }""",
            """  String getString() { return responseBody_; }
  int getSize() { return static_cast<int>(responseBody_.length()); }
  Stream *getStreamPtr() {
    responseStream_ = StreamString(responseBody_);
    return &responseStream_;
  }
  bool connected() const { return true; }
  static String errorToString(int) { return String("simulator HTTP error"); }""",
        )
        http_changed |= replace_once(
            http_client,
            """  String responseBody_;
  int statusCode_ = 0;""",
            """  String responseBody_;
  StreamString responseStream_;
  int statusCode_ = 0;""",
        )
        http_changed |= replace_once(
            http_client,
            """    responseBody_ = response.body;
    statusCode_ = response.statusCode;""",
            """    responseBody_ = response.body;
    responseStream_ = StreamString(responseBody_);
    statusCode_ = response.statusCode;""",
        )

    if http_changed:
        print(f"patch_simulator: patched HTTP client compatibility for {pioenv}")


patch_simulator()
env.AddPreAction("buildprog", patch_simulator)
