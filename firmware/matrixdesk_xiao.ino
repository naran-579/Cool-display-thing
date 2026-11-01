/*
  MatrixDesk (XIAO RP2040 edition) - follows the Hack Club LED matrix guide

  Hardware : Seeed XIAO RP2040 + 4-in-1 MAX7219 module (FC-16, 32x8)
  Libraries: MD_Parola, MD_MAX72XX (Library Manager)
  Board    : Seeed XIAO RP2040 (Earle Philhower "Raspberry Pi Pico/RP2040" core)

  Wiring (from the guide):
    DIN -> D10 (MOSI)   CLK -> D8 (SCK)   CS -> D7   VCC -> 5V   GND -> GND
    Slide pot wiper -> A0     (sets brightness; pot ends go to GND and 3V3)
    Encoder A -> D1, B -> D2, C -> GND  (sets speed)
    Button    -> D3 to GND    (next item in the playlist)

  Edit content.h to change messages and animations.
*/

#include <MD_Parola.h>
#include <MD_MAX72xx.h>
#include <SPI.h>
#include "content.h"

#define HARDWARE_TYPE MD_MAX72XX::FC16_HW
#define MAX_DEVICES   4
#define CS_PIN        D7           // DIN -> D10, CLK -> D8 (hardware SPI)
#define COLS          (MAX_DEVICES * 8)

// Comment out any input you have not built yet.
#define USE_POT
#define USE_ENCODER
#define USE_BUTTON

// If an animation looks mirrored or upside down, flip these.
#define FLIP_X false
#define FLIP_Y false

const int POT_PIN    = A0;
const int ENC_A      = D1;
const int ENC_B      = D2;
const int BUTTON_PIN = D3;

MD_Parola display = MD_Parola(HARDWARE_TYPE, CS_PIN, MAX_DEVICES);

const int ITEM_COUNT = sizeof(playlist) / sizeof(playlist[0]);
int current = 0;
int speed = 50;               // ms per scroll step, lower = faster
int brightness = 3;           // 0-15, keep it low on USB
int frameIndex = 0;
unsigned long nextFrameAt = 0;

int lastA = HIGH;
int lastButton = HIGH;
int lastLevel = -1;
unsigned long lastPress = 0;

void drawFrame(const Frame &f) {
  MD_MAX72XX *mx = display.getGraphicObject();
  mx->control(MD_MAX72XX::UPDATE, MD_MAX72XX::OFF);
  mx->clear();
  for (int y = 0; y < 8; y++) {
    for (int x = 0; x < COLS; x++) {
      if ((f.row[y] >> (COLS - 1 - x)) & 1) {
        int col = FLIP_X ? x : (COLS - 1 - x);   // MD_MAX72XX counts columns from the right
        int row = FLIP_Y ? (7 - y) : y;
        mx->setPoint(row, col, true);
      }
    }
  }
  mx->control(MD_MAX72XX::UPDATE, MD_MAX72XX::ON);
}

void showItem(int i) {
  const Item &it = playlist[i];
  display.displayClear();
  if (it.type == TEXT) {
    display.displayScroll(it.text, PA_LEFT, PA_SCROLL_LEFT, speed);
  } else {
    frameIndex = 0;
    nextFrameAt = 0;
  }
}

void setup() {
#ifdef USE_ENCODER
  pinMode(ENC_A, INPUT_PULLUP);
  pinMode(ENC_B, INPUT_PULLUP);
#endif
#ifdef USE_BUTTON
  pinMode(BUTTON_PIN, INPUT_PULLUP);
#endif
  display.begin();
  display.setIntensity(brightness);
  showItem(current);
}

void loop() {
#ifdef USE_POT
  // Slide pot -> brightness 0-15 (only send when it changes)
  int level = map(analogRead(POT_PIN), 0, 1023, 0, 15);
  if (level != lastLevel) {
    brightness = level;
    display.setIntensity(brightness);
    lastLevel = level;
  }
#endif

#ifdef USE_ENCODER
  // Encoder -> speed
  int a = digitalRead(ENC_A);
  if (a != lastA && a == LOW) {
    speed += (digitalRead(ENC_B) == HIGH) ? -5 : 5;
    speed = constrain(speed, 10, 200);
    display.setSpeed(speed);
  }
  lastA = a;
#endif

#ifdef USE_BUTTON
  // Button -> next playlist item (200 ms debounce)
  int button = digitalRead(BUTTON_PIN);
  if (button == LOW && lastButton == HIGH && millis() - lastPress > 200) {
    current = (current + 1) % ITEM_COUNT;
    showItem(current);
    lastPress = millis();
  }
  lastButton = button;
#endif

  const Item &it = playlist[current];
  if (it.type == TEXT) {
    if (display.displayAnimate()) display.displayReset();   // loop the scroll
  } else if (millis() >= nextFrameAt) {
    drawFrame(it.frames[frameIndex]);
    // Encoder speed also scales animation timing (50 = normal)
    nextFrameAt = millis() + (unsigned long)it.frames[frameIndex].ms * speed / 50;
    frameIndex = (frameIndex + 1) % it.count;
  }
}
