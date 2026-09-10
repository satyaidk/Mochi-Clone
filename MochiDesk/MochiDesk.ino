/* =============================================================================
   Mochi Desk — animated desktop companion for ESP32-C3 SuperMini
   -----------------------------------------------------------------------------
   18 animations, 1383 frames, 128x64 monochrome, ~14 FPS.

   Frames are XOR-delta encoded against the previous frame and then PackBits
   compressed, which brings 1.4 MB of raw bitmaps down to 231 KB of flash.
   The decoder is decodeFrame() below — about fifteen lines.

   HARDWARE (matches your confirmed wiring):
     SSD1306 128x64 OLED   SDA = GPIO20, SCL = GPIO21, address 0x3C
     TTP223 touch pad      GPIO3, active HIGH
     Speaker / buzzer      GPIO4   (use a transistor for a real speaker)

   CONTROLS:
     Single tap    next emotion
     Double tap    random emotion
     Long press    toggle shuffle mode (auto-changes every loop)
     Idle 5 min    drifts off to sleep; any tap wakes it

   BOARD SETTINGS:
     Board            : ESP32C3 Dev Module
     USB CDC On Boot  : Enabled
     Partition Scheme : Default 4MB with spiffs   (231 KB of frames fits fine)

   LIBRARIES: Adafruit SSD1306, Adafruit GFX
   ============================================================================= */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "animations.h"

/* ------------------------------ PINS --------------------------------------- */
#define PIN_SDA        20
#define PIN_SCL        21
#define PIN_TOUCH       1
#define PIN_BUZZER      2
#define OLED_ADDR    0x3C

/* ------------------------------ OPTIONS ------------------------------------ */
#define FRAME_MS          70      // 70 ms = ~14 FPS, the original recording rate
#define SOUND_ON        true
#define SHOW_NAME       true      // flash the emotion name when it changes
#define NAME_MS          700
#define SHUFFLE_ON_BOOT false
#define SLEEP_AFTER_MS  (5UL * 60UL * 1000UL)
#define I2C_HZ         700000UL   // drop to 400000 if the screen glitches

/* ------------------------------ DISPLAY ------------------------------------ */
Adafruit_SSD1306 display(128, 64, &Wire, -1);

/* ------------------------------ STATE -------------------------------------- */
uint8_t  frameBuf[1024];          // one decoded frame, row-major, MSB first
uint8_t  animIdx     = ANIM_HAPPY;
uint16_t frameIdx    = 0;
bool     shuffle     = SHUFFLE_ON_BOOT;
bool     asleep      = false;
bool     playOnce    = false;     // intro plays once, then hands over
uint8_t  nextAfterOnce = ANIM_HAPPY;

unsigned long lastFrame = 0, nameUntil = 0, lastTouchAt = 0, beepUntil = 0;

/* ============================ SOUND ========================================= */
void beep(unsigned int f, unsigned long ms) {
  if (!SOUND_ON) return;
  tone(PIN_BUZZER, f);
  beepUntil = millis() + ms;
}
void serviceBeep() {
  if (beepUntil && millis() > beepUntil) { noTone(PIN_BUZZER); beepUntil = 0; }
}

/* ============================ DECODER =======================================
   PackBits: a signed token byte. 0..127 means "the next (n+1) bytes are
   literals". -1..-127 means "repeat the next byte (1-n) times". Each decoded
   byte is XORed into the frame buffer, because what is stored is the
   difference from the previous frame, not the frame itself.
   This is why an animation must always be played from frame 0 with a cleared
   buffer — startAnim() takes care of that.
   ============================================================================= */
void decodeFrame(const Anim& a, uint16_t frame) {
  uint16_t i   = pgm_read_word(&a.offsets[frame]);
  uint16_t end = pgm_read_word(&a.offsets[frame + 1]);
  uint16_t o   = 0;

  while (o < 1024 && i < end) {
    int8_t t = (int8_t)pgm_read_byte(&a.data[i++]);
    if (t >= 0) {
      uint16_t n = (uint16_t)t + 1;
      while (n-- && o < 1024) frameBuf[o++] ^= pgm_read_byte(&a.data[i++]);
    } else {
      uint16_t n = (uint16_t)(1 - t);
      uint8_t  v = pgm_read_byte(&a.data[i++]);
      while (n-- && o < 1024) frameBuf[o++] ^= v;
    }
  }
}

/* ============================ PLAYBACK ====================================== */
void startAnim(uint8_t idx, bool once = false, uint8_t thenIdx = ANIM_HAPPY) {
  animIdx  = idx % ANIM_COUNT;
  frameIdx = 0;
  playOnce = once;
  nextAfterOnce = thenIdx;
  memset(frameBuf, 0, sizeof(frameBuf));   // delta chain restarts from black
  lastFrame = 0;
  if (SHOW_NAME && !once) nameUntil = millis() + NAME_MS;
  Serial.printf("play %s (%u frames)\n", ANIMS[animIdx].name, ANIMS[animIdx].frames);
}

uint8_t randomOther() {
  uint8_t n;
  do { n = random(1, ANIM_COUNT); } while (n == animIdx && ANIM_COUNT > 2);
  return n;   // start at 1 so the intro is never picked at random
}

void drawCurrent() {
  display.clearDisplay();
  display.drawBitmap(0, 0, frameBuf, 128, 64, SSD1306_WHITE);

  if (SHOW_NAME && millis() < nameUntil) {
    display.fillRect(0, 54, 128, 10, SSD1306_BLACK);
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(2, 56);
    display.print(ANIMS[animIdx].name);
    if (shuffle) { display.setCursor(112, 56); display.print("SH"); }
  }
  display.display();
}

void tickAnim() {
  if (millis() - lastFrame < FRAME_MS) return;
  lastFrame = millis();

  decodeFrame(ANIMS[animIdx], frameIdx);
  drawCurrent();

  frameIdx++;
  if (frameIdx >= ANIMS[animIdx].frames) {
    if (playOnce)      startAnim(nextAfterOnce);
    else if (shuffle)  startAnim(randomOther());
    else               startAnim(animIdx);      // loop, resetting the delta chain
  }
}

/* ============================ SLEEP ========================================= */
void goToSleep() {
  asleep = true;
  display.dim(true);
  startAnim(ANIM_SLEEPY);
  Serial.println("dozing off");
}
void wakeUp() {
  asleep = false;
  display.dim(false);
  beep(2400, 40);
  startAnim(ANIM_EXCITED2);
}

/* ============================ TOUCH ========================================= */
bool     touchPrev = false, longFired = false;
uint8_t  tapCount = 0;
unsigned long touchStart = 0, lastTapEnd = 0;

void serviceTouch() {
  bool now = digitalRead(PIN_TOUCH) == HIGH;

  if (now && !touchPrev) { touchStart = millis(); longFired = false; }

  // long press: toggle shuffle
  if (now && !longFired && millis() - touchStart > 1500) {
    longFired = true;
    lastTouchAt = millis();
    if (asleep) { wakeUp(); return; }
    shuffle = !shuffle;
    beep(shuffle ? 2600 : 700, 150);
    nameUntil = millis() + NAME_MS;
    Serial.printf("shuffle %s\n", shuffle ? "on" : "off");
  }

  // release
  if (!now && touchPrev && !longFired && millis() - touchStart > 40) {
    lastTouchAt = millis();
    if (asleep) { wakeUp(); tapCount = 0; return; }
    tapCount++;
    lastTapEnd = millis();
  }
  touchPrev = now;

  // resolve single vs double once the double-tap window closes
  if (tapCount && millis() - lastTapEnd > 320) {
    if (tapCount == 1) { beep(2200, 35); startAnim((animIdx + 1) % ANIM_COUNT); }
    else               { beep(2900, 60); startAnim(randomOther()); }
    tapCount = 0;
  }
}

/* ============================ SERIAL ======================================== */
void serviceSerial() {
  if (!Serial.available()) return;
  String s = Serial.readStringUntil('\n');
  s.trim();
  if (s.length() == 0) return;

  if (s == "list") {
    for (uint8_t i = 0; i < ANIM_COUNT; i++)
      Serial.printf("%2u  %s  %u frames\n", i, ANIMS[i].name, ANIMS[i].frames);
  } else if (s == "shuffle") {
    shuffle = !shuffle;
    Serial.printf("shuffle %s\n", shuffle ? "on" : "off");
  } else {
    int n = s.toInt();
    if (n >= 0 && n < ANIM_COUNT) startAnim(n);
    else Serial.println("type a number, 'list', or 'shuffle'");
  }
}

/* ============================ SETUP / LOOP ================================== */
void setup() {
  Serial.begin(115200);
  pinMode(PIN_TOUCH, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println("OLED not found on GPIO20/21 at 0x3C");
    tone(PIN_BUZZER, 400); delay(500); noTone(PIN_BUZZER);
    // keep going anyway so the serial console still works
  }
  display.clearDisplay();
  display.display();

  randomSeed(esp_random());
  Serial.printf("Mochi Desk ready: %u animations\n", ANIM_COUNT);
  Serial.println("serial: a number to jump, 'list', or 'shuffle'");

  beep(1800, 60);
  lastTouchAt = millis();
  startAnim(ANIM_INTRO, true, ANIM_HAPPY);   // intro once, then settle on happy
}

void loop() {
  serviceTouch();
  serviceBeep();
  serviceSerial();
  tickAnim();

  if (!asleep && millis() - lastTouchAt > SLEEP_AFTER_MS) goToSleep();
}
