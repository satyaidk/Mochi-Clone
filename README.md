# Mochi Desk

18 animations, 1383 frames, 128x64 monochrome, ~14 FPS on an ESP32-C3 SuperMini.

## Install
1. Copy the whole `MochiDesk` folder into your Arduino sketchbook.
2. Open `MochiDesk.ino` (the folder name and .ino name must match).
3. Libraries: Adafruit SSD1306, Adafruit GFX.
4. Board: ESP32C3 Dev Module, USB CDC On Boot = Enabled, Partition = Default 4MB with spiffs.

## Wiring
_______________________
| Signal     | GPIO   |
|------------|--------|
| OLED SDA   | GPIO20 |
| OLED SCL   | GPIO21 |
| TTP223 out | GPIO1  |
| Buzzer     | GPIO2  |
_______________________
## Controls
- Single tap: next emotion
- Double tap: random emotion
- Long press (1.5s): toggle shuffle
- Idle 5 minutes: falls asleep, any tap wakes it
- Serial (115200): type a number to jump, or `list`, or `shuffle`

## Animations
Intro, Happy, Happy2, Content, Excited, Laugh, Love, Proud, Relaxed, Music,
Determined, Confused, Embarrassed, Frustrated, Angry, Angry2, Sleepy, Sleepy2

## How the frames are stored
Each frame is a 128x64 1-bit bitmap (1024 bytes raw). Every frame is XORed
against the previous frame, then PackBits run-length compressed. That takes
1.4 MB of raw bitmaps down to 231 KB. `decodeFrame()` in the .ino reverses it.

Because frames are deltas, an animation must always be played from frame 0 with
a cleared buffer. `startAnim()` does that. If you add your own animation, encode
it the same way or the chain will not reconstruct.

## Credit
Frames converted from GIFs in github.com/huykhoong/esp32_dasai_mochi_clone_and_how_to,
which were captured from a Dasai Mochi product video. Personal use only.
