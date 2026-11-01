// content.h - EDIT THIS FILE to change what your display shows.
// Then re-upload the sketch. The button on your board steps through the list.

#pragma once
#include <Arduino.h>

// ---------- animation frames ----------
// The display is 32 pixels wide and 8 tall. One frame = 8 rows.
// Each ROW(a, b, c, d) draws one row: a, b, c, d are the four 8x8 modules
// from LEFT to RIGHT, and every 1 bit is a lit LED.
// "ms" is how long the frame stays on screen.
#define ROW(a, b, c, d) \
  (((uint32_t)(a) << 24) | ((uint32_t)(b) << 16) | ((uint32_t)(c) << 8) | (uint32_t)(d))

struct Frame {
  uint32_t row[8];
  uint16_t ms;
};

// Example: a beating heart (2 frames). Copy a frame block to add more frames.
const Frame heartbeat[] = {
  { { ROW(0, 0, 0b00000000, 0),
      ROW(0, 0, 0b01100110, 0),
      ROW(0, 0, 0b11111111, 0),
      ROW(0, 0, 0b11111111, 0),
      ROW(0, 0, 0b01111110, 0),
      ROW(0, 0, 0b00111100, 0),
      ROW(0, 0, 0b00011000, 0),
      ROW(0, 0, 0b00000000, 0) }, 250 },
  { { ROW(0, 0, 0b00000000, 0),
      ROW(0, 0, 0b00000000, 0),
      ROW(0, 0, 0b00100100, 0),
      ROW(0, 0, 0b01111110, 0),
      ROW(0, 0, 0b00111100, 0),
      ROW(0, 0, 0b00011000, 0),
      ROW(0, 0, 0b00000000, 0),
      ROW(0, 0, 0b00000000, 0) }, 250 },
};

// Example: a bar that sweeps across the whole display (4 frames).
const Frame sweep[] = {
  { { ROW(0b11110000, 0, 0, 0), ROW(0b11110000, 0, 0, 0), ROW(0b11110000, 0, 0, 0), ROW(0b11110000, 0, 0, 0),
      ROW(0b11110000, 0, 0, 0), ROW(0b11110000, 0, 0, 0), ROW(0b11110000, 0, 0, 0), ROW(0b11110000, 0, 0, 0) }, 120 },
  { { ROW(0, 0b11110000, 0, 0), ROW(0, 0b11110000, 0, 0), ROW(0, 0b11110000, 0, 0), ROW(0, 0b11110000, 0, 0),
      ROW(0, 0b11110000, 0, 0), ROW(0, 0b11110000, 0, 0), ROW(0, 0b11110000, 0, 0), ROW(0, 0b11110000, 0, 0) }, 120 },
  { { ROW(0, 0, 0b11110000, 0), ROW(0, 0, 0b11110000, 0), ROW(0, 0, 0b11110000, 0), ROW(0, 0, 0b11110000, 0),
      ROW(0, 0, 0b11110000, 0), ROW(0, 0, 0b11110000, 0), ROW(0, 0, 0b11110000, 0), ROW(0, 0, 0b11110000, 0) }, 120 },
  { { ROW(0, 0, 0, 0b11110000), ROW(0, 0, 0, 0b11110000), ROW(0, 0, 0, 0b11110000), ROW(0, 0, 0, 0b11110000),
      ROW(0, 0, 0, 0b11110000), ROW(0, 0, 0, 0b11110000), ROW(0, 0, 0, 0b11110000), ROW(0, 0, 0, 0b11110000) }, 120 },
};

// ---------- the playlist ----------
// Each button press moves to the next item. Mix text and animations freely.
enum ItemType { TEXT, ANIM };

struct Item {
  ItemType type;
  const char *text;     // used when type == TEXT
  const Frame *frames;  // used when type == ANIM
  uint8_t count;        // number of frames
};

#define TEXT_ITEM(s)      { TEXT, s, nullptr, 0 }
#define ANIM_ITEM(arr)    { ANIM, nullptr, arr, (uint8_t)(sizeof(arr) / sizeof(arr[0])) }

const Item playlist[] = {
  TEXT_ITEM("Hello, desk!"),
  ANIM_ITEM(heartbeat),
  TEXT_ITEM("Make it yours"),
  ANIM_ITEM(sweep),
};
