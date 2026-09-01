#include <assert.h>
#include <stdio.h>
#include "game.h"

static unsigned active_type(unsigned type)
{
    unsigned i, n = 0;
    for (i = 0; i < HK_MAX_OBJECTS; ++i)
        if (hk_objects[i].type == type) ++n;
    return n;
}

int main(void)
{
    unsigned i;
    int explosion_seen = 0;
    hk_game_begin();
    assert(hk_current_background == 0);
    assert(hk_player_x == 0x80 && hk_player_y == 0xB8);

    hk_game_step(HK_KEY_LEFT | HK_KEY_UP, 0);
    assert(hk_player_x == 0x7C && hk_player_y == 0xB4);
    assert(hk_player_anim == 0x10); /* original update order: vertical wins */

    hk_game_step(0, HK_KEY_FIRE);
    assert(active_type(1) == 1);
    for (i = 0; i < 4; ++i) hk_game_step(0, HK_KEY_FIRE);
    assert(active_type(1) <= 4);

    /* Killing an enemy converts that exact slot into the explosion. The
     * source coordinates must survive even when the freed shot slot is lower
     * in the object array. */
    hk_game_begin();
    hk_objects[0] = (HKObject){1, 1, 0, 4, 1, 173, 110, 1, 0, 0, 0};
    hk_objects[1] = (HKObject){2, 3, 0, 8, 1, 173, 100, 1, 0, 0, 0};
    hk_game_step(0, 0);
    assert(hk_objects[1].type == 11);
    assert(hk_objects[1].x == 173 && hk_objects[1].y == 102);

    hk_game_set_cheat(1);
    hk_game_begin();
    hk_objects[0] = (HKObject){2, 3, 0, 8, 1,
                               hk_player_x, hk_player_y, 1, 0, 0, 0};
    assert(hk_game_step(0, 0) == 0);
    assert(hk_player_visible == 1);
    hk_game_set_cheat(0);

    hk_game_begin();
    for (i = 0; i < 62; ++i) hk_game_step(0, 0);
    assert(active_type(2) >= 1); /* first source-table spawn */

    {
        unsigned first = hk_current_background;
        for (i = 0; i < 6; ++i) hk_game_begin();
        assert(hk_current_background == first);
    }

    /* A live input sequence must naturally reach the source explosion type. */
    hk_game_begin();
    for (i = 0; i < 20000 && !explosion_seen; ++i) {
        unsigned phase = (i / 110) & 1;
        u16 held = phase ? HK_KEY_RIGHT : HK_KEY_LEFT;
        u16 pressed = (i % 12) == 0 ? HK_KEY_FIRE : 0;
        unsigned slot;
        if (hk_game_step(held, pressed)) hk_game_begin();
        for (slot = 0; slot < HK_MAX_OBJECTS; ++slot) {
            unsigned type = hk_objects[slot].type;
            if (type == 11 || type == 13 || type == 14) {
                explosion_seen = 1;
                break;
            }
        }
    }
    assert(explosion_seen);
    printf("game logic: ok (natural explosion by frame %u)\n", i);
    return 0;
}
