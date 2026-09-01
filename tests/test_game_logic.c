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
    hk_game_begin();
    assert(hk_current_background == 0);
    assert(hk_player_x == 0x80 && hk_player_y == 0xD8);

    hk_game_step(HK_KEY_LEFT | HK_KEY_UP, 0);
    assert(hk_player_x == 0x7E && hk_player_y == 0xD6);
    assert(hk_player_anim == 0x10); /* original update order: vertical wins */

    hk_game_step(0, HK_KEY_FIRE);
    assert(active_type(1) == 1);
    for (i = 0; i < 4; ++i) hk_game_step(0, HK_KEY_FIRE);
    assert(active_type(1) <= 4);

    hk_game_begin();
    for (i = 0; i < 62; ++i) hk_game_step(0, 0);
    assert(active_type(2) >= 1); /* first source-table spawn */

    {
        unsigned first = hk_current_background;
        for (i = 0; i < 6; ++i) hk_game_begin();
        assert(hk_current_background == first);
    }
    puts("game logic: ok");
    return 0;
}
