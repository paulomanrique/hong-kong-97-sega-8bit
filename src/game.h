#ifndef HK97_GAME_H
#define HK97_GAME_H

#include "main.h"

/* The live waves fit in 12 SMS slots. Keeping the SNES allocation of 48 made
 * the Z80 scan 2,304 collision pairs even with only a few visible objects. */
#define HK_MAX_OBJECTS 12

typedef struct {
    u8 type, anim, frame, ftimer, visible;
    s16 x, y, hp, st0, st1, st2;
} HKObject;

extern HKObject hk_objects[HK_MAX_OBJECTS];
extern s16 hk_player_x, hk_player_y;
extern u8 hk_player_anim, hk_player_visible;
extern u8 hk_current_background, hk_background_flash;

void hk_game_begin(void);
u8 hk_game_step(u16 held, u16 pressed);
void hk_game_set_cheat(u8 enabled);

#endif
