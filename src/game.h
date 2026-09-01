#ifndef HK97_GAME_H
#define HK97_GAME_H

#include "main.h"

#define HK_MAX_OBJECTS 48

typedef struct {
    u8 type, anim, frame, ftimer, visible;
    s16 x, y, hp, st0, st1, st2;
} HKObject;

extern HKObject hk_objects[HK_MAX_OBJECTS];
extern s16 hk_player_x, hk_player_y;
extern u8 hk_player_anim, hk_player_visible;
extern u8 hk_digits[9];
extern u8 hk_current_background, hk_background_flash;

void hk_game_begin(void);
u8 hk_game_step(u16 held, u16 pressed);

#endif
