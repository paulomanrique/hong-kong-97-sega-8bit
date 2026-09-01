/* Native game logic derived from docs/source-mapping.md. No 65816 code runs
 * in the target. Rendering is a separate SMS backend in main.c. */
#include <string.h>
#include "game.h"
#include "game_tables.h"

#define P_ALIVE 0
#define P_DEAD 1
#define P_FLICK 2
#define BOSS_KILLS 30

HKObject hk_objects[HK_MAX_OBJECTS];
s16 hk_player_x, hk_player_y;
u8 hk_player_anim, hk_player_visible, hk_digits[9];
u8 hk_current_background, hk_background_flash;

static u8 pstate, shots, kills, boss_active, next_background;
static u8 seq_x, seq_type, seq_vehicle, seq_drop;
static u16 pflicker, death_timer, pending_points, spawn_delay;
static const u8 type_anim[15] = {
    0x0A,0x09,0x03,0x04,0x05,0x01,0x0D,0x0D,
    0x0E,0x00,0x08,0x06,0x06,0x06,0x06
};

static s16 iabs16(s16 v) { return v < 0 ? -v : v; }

static HKObject *spawn(u8 type, s16 x, s16 y)
{
    u8 i;
    for (i = 0; i < HK_MAX_OBJECTS; ++i) {
        HKObject *o = &hk_objects[i];
        if (o->type) continue;
        memset(o, 0, sizeof(*o));
        o->type = type; o->anim = type_anim[type]; o->visible = 1;
        o->ftimer = ANIM_DURS[o->anim][0]; o->x = x; o->y = y;
        o->hp = type == 5 ? 32 : type == 9 ? 8 : 1;
        return o;
    }
    return 0;
}

static void kill_object(HKObject *o) { o->type = 0; o->visible = 0; }

static u8 animation_step(HKObject *o)
{
    u8 done = 0;
    if (--o->ftimer) return 0;
    if (++o->frame >= ANIM_NFRAMES[o->anim]) { o->frame = 0; done = 1; }
    o->ftimer = ANIM_DURS[o->anim][o->frame];
    return done;
}

static void score_step(void)
{
    u8 *d = hk_digits;
    if (!pending_points) return;
    --pending_points; ++d[0];
    if (d[0] == 9) { d[0] = 0; ++d[1];
    if (d[1] == 9) { d[1] = 0; ++d[2];
    if (d[2] == 9) { d[2] = 0; ++d[3];
    if (d[3] == 9) { d[3] = 0; ++d[3]; /* original bug */
    if (d[4] == 9) { d[4] = 0; ++d[5];
    if (d[5] == 9) { d[5] = 0; ++d[6];
    if (d[6] == 9) { d[6] = 0; ++d[7];
    if (d[7] == 9) { d[7] = 0; ++d[8]; }}}}}}}}
}

static void spawner_step(void)
{
    u8 param;
    if (boss_active || pstate == P_DEAD) return;
    if (spawn_delay) { --spawn_delay; return; }
    if (kills >= BOSS_KILLS) {
        kills = 0; boss_active = 1; spawn(5, 0x80, 0x80); return;
    }
    if (seq_x >= sizeof(SPAWN_TYPE_SEQ)) seq_x = 0;
    if (seq_type >= sizeof(SPAWN_DELAY)) seq_type = 0;
    spawn_delay = SPAWN_DELAY[seq_type]; param = SPAWN_PARAM[seq_type];
    if (param == 9) {
        spawn(9, 0x100, SPAWN9_X[seq_vehicle]);
        if (++seq_vehicle >= sizeof(SPAWN9_X) / sizeof(SPAWN9_X[0])) seq_vehicle = 0;
    } else spawn((u8)(param + 2), SPAWN_TYPE_SEQ[seq_x], 0);
    ++seq_x; ++seq_type;
}

static void drop_item(s16 x, s16 y)
{
    u8 v = ITEM_DROPS[seq_drop];
    if (++seq_drop >= sizeof(ITEM_DROPS)) seq_drop = 0;
    if (v) spawn((u8)(v + 6), x, y);
}

static void player_step(u16 held, u16 pressed)
{
    u8 anim = 0x0A;
    if (pstate == P_DEAD) return;
    if (pstate == P_FLICK) {
        if (pflicker) { --pflicker; hk_player_visible = (pflicker & 4) ? 0 : 1; }
        else { pstate = P_ALIVE; hk_player_visible = 1; }
    }
    if ((held & HK_KEY_LEFT) && hk_player_x > 0x10) { hk_player_x -= 2; anim = 0x02; }
    if ((held & HK_KEY_RIGHT) && hk_player_x < 0xF0) { hk_player_x += 2; anim = 0x0C; }
    if ((held & HK_KEY_UP) && hk_player_y > 0x28) { hk_player_y -= 2; anim = 0x10; }
    if ((held & HK_KEY_DOWN) && hk_player_y < 0xE0) { hk_player_y += 2; anim = 0x0F; }
    if ((pressed & HK_KEY_FIRE) && shots < 4 && spawn(1, hk_player_x, hk_player_y)) ++shots;
    hk_player_anim = anim;
}

static void hit_player(u8 mode, HKObject *source)
{
    if (pstate != P_ALIVE) return;
    if (mode == 1 || mode == 4) { pstate = P_DEAD; death_timer = 1; }
    else if (mode == 2) {
        pstate = P_DEAD; death_timer = 0; spawn(12, source->x, source->y); kill_object(source);
    } else if (mode == 3) {
        pstate = P_FLICK; pflicker = 480; kill_object(source);
    }
}

static void shot_hit(HKObject *e)
{
    if (e->type >= 2 && e->type <= 4) {
        ++kills; pending_points += 5; drop_item(e->x, e->y);
        spawn(11, e->x, e->y); kill_object(e);
    } else if (e->type == 9) {
        if (--e->hp == 0) {
            ++kills; pending_points += 50; drop_item(e->x, e->y);
            spawn(13, e->x, e->y); kill_object(e);
        }
    } else if (e->type == 5 && e->st0 != 0 && e->st0 != 6 && --e->hp == 0) {
        pending_points += 100; boss_active = 0; spawn(13, e->x, e->y);
        e->st0 = 6; e->st1 = 0;
    }
}

static u8 overlap(s16 ax, s16 ay, u8 aa, s16 bx, s16 by, u8 ba)
{
    return ax - ANIM_HB_L[aa] < bx + ANIM_HB_R[ba]
        && bx - ANIM_HB_L[ba] < ax + ANIM_HB_R[aa]
        && ay - ANIM_HB_T[aa] < by + ANIM_HB_B[ba]
        && by - ANIM_HB_T[ba] < ay + ANIM_HB_B[aa];
}

static void boss_sweep(HKObject *o)
{
    if (!o->st2) { if (--o->x <= 0x30) o->st2 = 1; }
    else if (++o->x >= 0xD0) o->st2 = 0;
}

static void object_step(HKObject *o)
{
    u8 done = animation_step(o);
    switch (o->type) {
    case 1: o->y -= 4; if (o->y < -8) { --shots; kill_object(o); } break;
    case 2: if (++o->y >= 0x100) kill_object(o); break;
    case 3: {
        s16 v, w; o->y += 2;
        if (hk_player_x >= o->x) { if (o->st0 < 0x1B) ++o->st0; }
        else if (o->st0 > -0x1B) --o->st0;
        v = o->st0; w = WOBBLE3[v < 0 ? -v : v]; o->x += v < 0 ? -w : w;
        if (o->st1 < 4 && iabs16(hk_player_x - o->x) < 8) {
            if (o->st2) --o->st2; else { o->st2 = 0x18; ++o->st1; spawn(10, o->x, o->y); }
        }
        if (o->y >= 0x100) kill_object(o);
        break;
    }
    case 4:
        o->y += 2; o->x += ZIGZAG4[o->st0]; ++o->st0;
        if (o->st0 >= (s16)(sizeof(ZIGZAG4) / sizeof(ZIGZAG4[0])) || ZIGZAG4[o->st0] == 0) o->st0 = 0;
        if (o->y >= 0x100) kill_object(o);
        break;
    case 5:
        switch (o->st0) {
        case 0:
            ++o->st1; o->visible = (o->st1 & 2) ? 0 : 1; hk_background_flash = !o->visible;
            if (o->st1 >= 0x1E) { o->visible = 1; hk_background_flash = 0; o->st0 = 1; } return;
        case 1: boss_sweep(o); if (iabs16(hk_player_x - o->x) < 0x18) { o->st0 = 2; o->st1 = 0x1E; } break;
        case 2: boss_sweep(o); if (--o->st1 == 0) { o->st0 = 3; o->st1 = 0; } break;
        case 3:
            o->y += BOSS_DESC[o->st1]; if (o->st1 < 0x10) ++o->st1;
            if (o->y >= 0xDC) { o->y = 0xDC; o->st0 = 4; o->st1 = 0x3C; } break;
        case 4: if (--o->st1 == 0) o->st0 = 5; break;
        case 5: if (--o->y <= 0x80) { o->y = 0x80; o->st0 = 1; } break;
        case 6:
            ++o->st1; o->visible = (o->st1 & 1) ? 0 : 1; if (o->st1 & 1) ++o->y;
            if (o->st1 >= 0x78) kill_object(o);
            break;
        } break;
    case 7: case 8: if (++o->y >= 0xE0) kill_object(o); break;
    case 9: --o->x; if (iabs16(hk_player_x - o->x) < 0x18) o->x -= 3; if (o->x < -16) kill_object(o); break;
    case 10: o->y += 3; if (o->y >= 0xE0) kill_object(o); break;
    case 11: case 14: if (done) kill_object(o); break;
    case 12: if (done) { death_timer = 120; kill_object(o); } break;
    case 13:
        o->st1 ^= 1;
        if (o->st0 < 0x18 && !o->st1) {
            spawn(14, o->x + BIGEXP_OFF[o->st0 * 2], o->y + BIGEXP_OFF[o->st0 * 2 + 1]); ++o->st0;
        }
        if (done && o->st0 >= 0x18) kill_object(o);
        break;
    }
}

static void collisions_step(void)
{
    static const u8 ph[15] = {0,0,1,1,1,4,0,2,3,1,1,0,0,0,0};
    u8 i, j;
    for (i = 0; i < HK_MAX_OBJECTS; ++i) {
        HKObject *o = &hk_objects[i]; u8 h;
        if (!o->type) continue;
        h = ph[o->type];
        if (h && pstate == P_ALIVE && overlap(hk_player_x,hk_player_y,hk_player_anim,o->x,o->y,o->anim)
            && (o->type != 5 || (o->st0 >= 1 && o->st0 <= 5))) hit_player(h,o);
        if ((o->type >= 2 && o->type <= 5) || o->type == 9) {
            for (j = 0; j < HK_MAX_OBJECTS; ++j) {
                HKObject *s = &hk_objects[j];
                if (s->type == 1 && overlap(s->x,s->y,s->anim,o->x,o->y,o->anim)) {
                    --shots; kill_object(s); shot_hit(o); break;
                }
            }
        }
    }
}

void hk_game_begin(void)
{
    memset(hk_objects,0,sizeof(hk_objects)); memset(hk_digits,0,sizeof(hk_digits));
    hk_current_background = next_background; if (++next_background >= 6) next_background = 0;
    hk_player_x=0x80; hk_player_y=0xD8; hk_player_anim=0x0A; hk_player_visible=1; hk_background_flash=0;
    pstate=P_ALIVE; pflicker=0; shots=kills=boss_active=0; death_timer=pending_points=0; spawn_delay=60;
    seq_x=seq_type=seq_vehicle=seq_drop=0;
}

u8 hk_game_step(u16 held, u16 pressed)
{
    u8 i; player_step(held,pressed); spawner_step();
    for (i=0;i<HK_MAX_OBJECTS;++i) if (hk_objects[i].type) object_step(&hk_objects[i]);
    collisions_step(); score_step();
    if (pstate == P_DEAD) { hk_player_visible=0; if (death_timer && --death_timer == 0) return 1; }
    return 0;
}
