// Auto-generated index of all Mochi animations.
// Each frame is XOR-delta encoded against the previous frame, then PackBits
// compressed. 1383 frames total, 231 KB of flash instead of 1.4 MB raw.
#pragma once
#include <Arduino.h>

#include "anim_intro.h"
#include "anim_happy.h"
#include "anim_happy2.h"
#include "anim_content.h"
#include "anim_excited2.h"
#include "anim_laugh.h"
#include "anim_love.h"
#include "anim_proud.h"
#include "anim_relaxed.h"
#include "anim_music.h"
#include "anim_determined.h"
#include "anim_confused2.h"
#include "anim_embarrassed.h"
#include "anim_frustrated.h"
#include "anim_angry.h"
#include "anim_angry2.h"
#include "anim_sleepy.h"
#include "anim_sleepy3.h"

struct Anim {
  const char*     name;
  const uint8_t*  data;
  const uint16_t* offsets;
  uint16_t        frames;
};

const Anim ANIMS[] = {
  { "Intro      ", intro_data, intro_offsets, INTRO_FRAMES },
  { "Happy      ", happy_data, happy_offsets, HAPPY_FRAMES },
  { "Happy2     ", happy2_data, happy2_offsets, HAPPY2_FRAMES },
  { "Content    ", content_data, content_offsets, CONTENT_FRAMES },
  { "Excited    ", excited2_data, excited2_offsets, EXCITED2_FRAMES },
  { "Laugh      ", laugh_data, laugh_offsets, LAUGH_FRAMES },
  { "Love       ", love_data, love_offsets, LOVE_FRAMES },
  { "Proud      ", proud_data, proud_offsets, PROUD_FRAMES },
  { "Relaxed    ", relaxed_data, relaxed_offsets, RELAXED_FRAMES },
  { "Music      ", music_data, music_offsets, MUSIC_FRAMES },
  { "Determined ", determined_data, determined_offsets, DETERMINED_FRAMES },
  { "Confused   ", confused2_data, confused2_offsets, CONFUSED2_FRAMES },
  { "Embarrassed", embarrassed_data, embarrassed_offsets, EMBARRASSED_FRAMES },
  { "Frustrated ", frustrated_data, frustrated_offsets, FRUSTRATED_FRAMES },
  { "Angry      ", angry_data, angry_offsets, ANGRY_FRAMES },
  { "Angry2     ", angry2_data, angry2_offsets, ANGRY2_FRAMES },
  { "Sleepy     ", sleepy_data, sleepy_offsets, SLEEPY_FRAMES },
  { "Sleepy2    ", sleepy3_data, sleepy3_offsets, SLEEPY3_FRAMES },
};

const uint8_t ANIM_COUNT = sizeof(ANIMS) / sizeof(ANIMS[0]);

// Index of each animation, in the order listed above
#define ANIM_INTRO        0
#define ANIM_HAPPY        1
#define ANIM_HAPPY2       2
#define ANIM_CONTENT      3
#define ANIM_EXCITED2     4
#define ANIM_LAUGH        5
#define ANIM_LOVE         6
#define ANIM_PROUD        7
#define ANIM_RELAXED      8
#define ANIM_MUSIC        9
#define ANIM_DETERMINED   10
#define ANIM_CONFUSED2    11
#define ANIM_EMBARRASSED  12
#define ANIM_FRUSTRATED   13
#define ANIM_ANGRY        14
#define ANIM_ANGRY2       15
#define ANIM_SLEEPY       16
#define ANIM_SLEEPY3      17
