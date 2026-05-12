#include "SdCardFontSystem.h"

#include <GfxRenderer.h>
#include <Logging.h>

#include "CrossPointSettings.h"

static uint8_t pointSizeFromFontSize(const CrossPointSettings::FONT_SIZE size) {
  switch (size) {
    case CrossPointSettings::TEENSY:
      return 8;
    case CrossPointSettings::TINY:
      return 10;
    case CrossPointSettings::SMALL:
      return 12;
    case CrossPointSettings::LARGE:
      return 16;
    case CrossPointSettings::EXTRA_LARGE:
      return 18;
    case CrossPointSettings::HUGE_SIZE:
      return 20;
    case CrossPointSettings::MEDIUM:
    default:
      return 14;
  }
}

static uint8_t targetPointSizeFromSettings() { return pointSizeFromFontSize(SETTINGS.getEffectiveReaderFontSize()); }

void SdCardFontSystem::begin(GfxRenderer& renderer) {
  registry_.discover();

  // Register this system as the SD font ID resolver in settings.
  // Uses a static trampoline since CrossPointSettings stores a plain function pointer.
  SETTINGS.sdFontIdResolver = [](void* ctx, const char* familyName, uint8_t fontSizeEnum) -> int {
    return static_cast<SdCardFontSystem*>(ctx)->resolveFontId(familyName, fontSizeEnum);
  };
  SETTINGS.sdFontResolverCtx = this;

  // If user has a saved SD font selection, load it
  if (SETTINGS.sdFontFamilyName[0] != '\0') {
    const auto* family = registry_.findFamily(SETTINGS.sdFontFamilyName);
    if (family) {
      if (manager_.loadFamily(*family, renderer, targetPointSizeFromSettings())) {
        LOG_DBG("SDFS", "Loaded SD card font family: %s", SETTINGS.sdFontFamilyName);
      } else {
        LOG_ERR("SDFS", "Failed to load SD font family: %s (clearing)", SETTINGS.sdFontFamilyName);
        SETTINGS.sdFontFamilyName[0] = '\0';
      }
    } else {
      LOG_DBG("SDFS", "SD font family not found on card: %s (clearing)", SETTINGS.sdFontFamilyName);
      SETTINGS.sdFontFamilyName[0] = '\0';
    }
  }

  LOG_DBG("SDFS", "SD font system ready (%d families discovered)", registry_.getFamilyCount());
}

void SdCardFontSystem::ensureLoaded(GfxRenderer& renderer) {
  // If the web server (or another task) installed/deleted fonts, re-discover.
  // Track whether we just re-discovered so we can force a reload below even
  // when the wanted family/size still maps to the same point size — the file
  // contents on disk may have changed (e.g. user re-uploaded a new build).
  const bool registryWasDirty = registryDirty_.exchange(false, std::memory_order_acquire);
  if (registryWasDirty) {
    LOG_DBG("SDFS", "Registry dirty — re-discovering fonts");
    registry_.discover();
  }

  const char* wantedFamily = SETTINGS.sdFontFamilyName;
  const std::string& currentFamily = manager_.currentFamilyName();
  const uint8_t targetPointSize = targetPointSizeFromSettings();

  if (wantedFamily[0] == '\0') {
    if (!currentFamily.empty()) {
      manager_.unloadAll(renderer);
    }
    return;
  }

  // Reload if family changed OR if the user-selected size maps to a
  // different file than what's currently loaded OR if the registry was
  // just rediscovered (file may have been replaced on disk).
  bool familyMatches = (currentFamily == wantedFamily);
  if (familyMatches) {
    const auto* family = registry_.findFamily(wantedFamily);
    if (!family) {
      LOG_DBG("SDFS", "SD font family disappeared: %s (clearing)", wantedFamily);
      manager_.unloadAll(renderer);
      SETTINGS.sdFontFamilyName[0] = '\0';
      return;
    }
    const uint8_t wantedPt = SdCardFontManager::choosePointSize(*family, targetPointSize);
    if (!registryWasDirty && wantedPt == manager_.currentPointSize()) return;
    LOG_DBG("SDFS", "Reloading %s: size %u -> %u (target %u)%s", wantedFamily, manager_.currentPointSize(), wantedPt,
            targetPointSize, registryWasDirty ? " [registry dirty]" : "");
  }

  if (!currentFamily.empty()) {
    manager_.unloadAll(renderer);
  }

  const auto* family = registry_.findFamily(wantedFamily);
  if (family) {
    if (manager_.loadFamily(*family, renderer, targetPointSize)) {
      LOG_DBG("SDFS", "Loaded SD font family: %s", wantedFamily);
    } else {
      LOG_ERR("SDFS", "Failed to load SD font family: %s (clearing)", wantedFamily);
      SETTINGS.sdFontFamilyName[0] = '\0';
    }
  } else {
    LOG_DBG("SDFS", "SD font family not found: %s (clearing)", wantedFamily);
    SETTINGS.sdFontFamilyName[0] = '\0';
  }
}

bool SdCardFontSystem::changeReaderFontSize(const bool larger) {
  if (SETTINGS.sdFontFamilyName[0] == '\0') {
    return SETTINGS.changeReaderFontSize(larger);
  }

  if (registryDirty_.exchange(false, std::memory_order_acquire)) {
    registry_.discover();
  }

  const auto* family = registry_.findFamily(SETTINGS.sdFontFamilyName);
  if (!family) {
    return SETTINGS.changeReaderFontSize(larger);
  }

  const uint8_t originalFontSize = SETTINGS.fontSize;
  const uint8_t activeSizeCount = CrossPointSettings::getActiveReaderFontSizeCount();
  for (uint8_t attempt = 0; attempt < activeSizeCount; attempt++) {
    if (!SETTINGS.changeReaderFontSize(larger)) break;

    if (family->hasSize(targetPointSizeFromSettings())) {
      return true;
    }

    if (SETTINGS.fontSize == originalFontSize) break;
  }

  SETTINGS.fontSize = originalFontSize;
  return false;
}

int SdCardFontSystem::resolveFontId(const char* familyName, uint8_t /*fontSizeEnum*/) const {
  // The manager loads exactly one size (closest to the effective reader point
  // size), so the enum is implicit — always return the single loaded font ID for this family.
  // ensureLoaded() must have been called with the current settings before this.
  return manager_.getFontId(familyName);
}
