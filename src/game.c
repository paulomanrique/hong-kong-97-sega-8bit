// HK97 gameplay, reimplemented from the disassembly (docs/mapping.md).
// Original object types:
//   1 shot; 2/3/4 enemies (+5); 5 boss 32HP (+100); 7 fatal item (corpse);
//   8 harmless item (blinks); 9 8HP vehicle from the right (+50); A bullet;
//   B falling item (visual); C player corpse; D large explosion; E fragment.
#include <genesis.h>
#include "resources.h"
#include "main.h"

#define MAXOBJ        20
#ifndef BOSS_KILLS
#define BOSS_KILLS    30           // $0ED4 >= 0x1E in the original
#endif
#define PSTATE_ALIVE  0
#define PSTATE_DEAD   1
#define PSTATE_FLICK  2

typedef struct
{
    u8 type;            // 0 = free slot
    u8 anim, frame;
    u8 ftimer;
    s16 x, y;           // center
    s16 hp;
    s16 st0, st1, st2;  // per-type state
    Sprite *spr;
} Obj;

static Obj objs[MAXOBJ];
static s16 px, py;                 // player (center)
static u8 pstate;
static u16 pflicker;               // frames left blinking
static u8 panim;
static u16 shots;                  // active shots (max 4)
static u16 kills;                  // toward the boss every 30
static bool bossActive;
static u16 deathTimer;
static u8 digits[9];               // BCD score (base 9, like the original!)
static u16 pending;                // pending points (+1/frame into the score)
static u16 spawnDelay;
static u16 seqX, seqT, seq9, seqDrop;
static Sprite *pspr;
static u16 bgRound;                // background advances each run ($1253)
static u16 digitTiles;             // VRAM index of the digit tileset
static u16 turboT;                 // cheat-mode turbo cadence

static const SpriteDefinition *const ANIM_SPR[17] = {
    &spr_a00, &spr_a01, &spr_a02, &spr_a03, &spr_a04, &spr_a05,
    &spr_a06, &spr_a07, &spr_a08, &spr_a09, &spr_a0A, &spr_a0B,
    &spr_a0C, &spr_a0D, &spr_a0E, &spr_a0F, &spr_a10,
};
static const Image *const GAMEBG[6] = {
    &bg_game0, &bg_game1, &bg_game2, &bg_game3, &bg_game4, &bg_game5
};
static const Palette *const GAMEBG_RAW[6] = {
    &pal_raw0, &pal_raw1, &pal_raw2, &pal_raw3, &pal_raw4, &pal_raw5
};
static u16 curBg;                  // current run's background

// anim per type (from the disasm's ObjInit_*)
static const u8 TYPE_ANIM[15] = {
    0x0A, 0x09, 0x03, 0x04, 0x05, 0x01, 0x0D, 0x0D,
    0x0E, 0x00, 0x08, 0x06, 0x06, 0x06, 0x06
};

static void sprCenter(Sprite *s, const SpriteDefinition *def, s16 x, s16 y)
{
    SPR_setPosition(s, x - def->w / 2, y - def->h / 2);
}

static Obj *spawn(u8 type, s16 x, s16 y)
{
    for (u16 i = 0; i < MAXOBJ; i++)
    {
        Obj *o = &objs[i];
        if (o->type)
            continue;
        o->type = type;
        o->anim = TYPE_ANIM[type];
        o->frame = 0;
        o->ftimer = ANIM_DURS[o->anim][0];
        o->x = x;
        o->y = y;
        o->st0 = o->st1 = o->st2 = 0;
        o->hp = (type == 5) ? 32 : (type == 9) ? 8 : 1;
        o->spr = SPR_addSprite(ANIM_SPR[o->anim], x, y,
                               TILE_ATTR(PAL1, TRUE, FALSE, FALSE));
        if (o->spr)
            sprCenter(o->spr, ANIM_SPR[o->anim], x, y);
        return o;
    }
    return NULL;
}

static void kill(Obj *o)
{
    if (o->spr)
        SPR_releaseSprite(o->spr);
    o->spr = NULL;
    o->type = 0;
}

// advance the anim; TRUE when the anim completed a cycle
static bool animStep(Obj *o)
{
    if (--o->ftimer)
        return FALSE;
    o->frame++;
    bool done = FALSE;
    if (o->frame >= ANIM_NFRAMES[o->anim])
    {
        o->frame = 0;
        done = TRUE;
    }
    o->ftimer = ANIM_DURS[o->anim][o->frame];
    if (o->spr)
        SPR_setFrame(o->spr, o->frame);
    return done;
}

// ---------------------------------------------------------- score
static void drawDigits(void)
{
    // digit i at (col 28-2i, row 1), 2x2 tiles from the ts_digits tileset
    for (u16 i = 0; i < 9; i++)
    {
        u16 d = digits[i];
        u16 col = 28 - i * 2;
        u16 attr = TILE_ATTR_FULL(PAL3, TRUE, FALSE, FALSE, digitTiles);
        VDP_setTileMapXY(BG_A, attr + d * 2, col, 1);
        VDP_setTileMapXY(BG_A, attr + d * 2 + 1, col + 1, 1);
        VDP_setTileMapXY(BG_A, attr + 20 + d * 2, col, 2);
        VDP_setTileMapXY(BG_A, attr + 20 + d * 2 + 1, col + 1, 2);
    }
}

static void scoreTick(void)
{
    if (!pending)
        return;
    pending--;
    // carry at 9 (and the digit 3->4 bug), faithful to $B484
    u8 *d = digits;
    d[0]++;
    if (d[0] == 9) { d[0] = 0; d[1]++;
    if (d[1] == 9) { d[1] = 0; d[2]++;
    if (d[2] == 9) { d[2] = 0; d[3]++;
    if (d[3] == 9) { d[3] = 0; d[3]++;          // (sic) original bug
    if (d[4] == 9) { d[4] = 0; d[5]++;
    if (d[5] == 9) { d[5] = 0; d[6]++;
    if (d[6] == 9) { d[6] = 0; d[7]++;
    if (d[7] == 9) { d[7] = 0; d[8]++; }}}}}}}}
    drawDigits();
}

// ---------------------------------------------------------- spawner
static void spawner(void)
{
    if (bossActive || pstate == PSTATE_DEAD)
        return;
    if (spawnDelay) { spawnDelay--; return; }
    if (kills >= BOSS_KILLS)
    {
        kills = 0;
        bossActive = TRUE;
        spawn(5, 0x80, 0x80);      // starts in state 0 (flash-in)
        return;
    }
    u16 xi = seqX;
    if (SPAWN_TYPE_SEQ[xi] == 0xFF || xi >= sizeof(SPAWN_TYPE_SEQ))
        xi = seqX = 0;
    u16 ti = seqT;
    if (ti >= sizeof(SPAWN_DELAY))
        ti = seqT = 0;
    spawnDelay = SPAWN_DELAY[ti];
    u8 code = SPAWN_PARAM[ti];
    if (code == 9)
    {
        u16 y = SPAWN9_X[seq9];
        seq9 = (seq9 + 1) % (sizeof(SPAWN9_X) / 2);
        spawn(9, 0x100, y);
    }
    else
        spawn(code + 2, SPAWN_TYPE_SEQ[xi], 0);
    seqX++;
    seqT++;
}

static void dropItem(s16 x, s16 y)
{
    u8 v = ITEM_DROPS[seqDrop];
    seqDrop = (seqDrop + 1) % sizeof(ITEM_DROPS);
    if (v)
        spawn(v + 6, x, y);        // 1 -> type 7 (fatal!), 2 -> type 8
}

// ---------------------------------------------------------- updates
static void updatePlayer(u16 held, u16 pressed)
{
    if (pstate == PSTATE_DEAD)
        return;
    if (pstate == PSTATE_FLICK)
    {
        if (pflicker)
        {
            pflicker--;
            SPR_setVisibility(pspr, (pflicker & 4) ? HIDDEN : VISIBLE);
        }
        else
        {
            pstate = PSTATE_ALIVE;
            SPR_setVisibility(pspr, VISIBLE);
        }
    }
    u8 anim = 0x0A;
    if (held & BUTTON_LEFT)  { if (px > 0x10) px -= 2; anim = 0x02; }
    if (held & BUTTON_RIGHT) { if (px < 0xF0) px += 2; anim = 0x0C; }
    if (held & BUTTON_UP)    { if (py > 0x28) py -= 2; anim = 0x10; }
    if (held & BUTTON_DOWN)  { if (py < 0xE0) py += 2; anim = 0x0F; }
    if ((pressed & (BUTTON_A | BUTTON_B | BUTTON_C)) && shots < 4)
    {
        spawn(1, px, py);
        shots++;
    }
    // cheat turbo: holding A, rapid-fires (one shot every 4 frames)
    if (g_cheat && (held & BUTTON_A) && shots < 4 && !(turboT & 3))
    {
        spawn(1, px, py);
        shots++;
    }
    turboT++;
    if (anim != panim)
    {
        panim = anim;
        SPR_releaseSprite(pspr);
        pspr = SPR_addSprite(ANIM_SPR[anim], px, py,
                             TILE_ATTR(PAL1, TRUE, FALSE, FALSE));
    }
    sprCenter(pspr, ANIM_SPR[panim], px, py);
}

static void playerHit(u8 mode, Obj *src)
{
    if (g_cheat)                       // cheat mode is invincible
        return;
    if (pstate != PSTATE_ALIVE)
        return;
    switch (mode)
    {
    case 1:                            // immediate death
        pstate = PSTATE_DEAD;
        deathTimer = 1;
        break;
    case 2:                            // type 7: corpse in the enemy's place
        pstate = PSTATE_DEAD;
        deathTimer = 0;
        spawn(12, src->x, src->y);     // type C: corpse -> timer on finish
        kill(src);
        break;
    case 3:                            // type 8: just blinks 480 frames
        pstate = PSTATE_FLICK;
        pflicker = 480;
        kill(src);
        break;
    case 4:                            // boss
        pstate = PSTATE_DEAD;
        deathTimer = 1;
        break;
    }
}

static void shotHit(Obj *e)
{
    switch (e->type)
    {
    case 2: case 3: case 4:
        kills++;
        pending += 5;
        dropItem(e->x, e->y);
        spawn(11, e->x, e->y);         // type B: small explosion
        kill(e);
        break;
    case 9:
        if (--e->hp == 0)
        {
            kills++;
            pending += 50;
            dropItem(e->x, e->y);
            spawn(13, e->x, e->y);     // type D: large explosion
            kill(e);
        }
        break;
    case 5:
        if (e->st0 == 0 || e->st0 == 6)
            break;                     // no damage during flash-in / dying
        if (--e->hp == 0)
        {
            pending += 100;
            bossActive = FALSE;        // spawner returns at once ($0ECC=0)
            spawn(13, e->x, e->y);
            e->st0 = 6;                // death state (blinks and vanishes)
            e->st1 = 0;
        }
        break;
    }
}

// AABB with the original's per-anim edges (table [$3E], see gen_tables)
static bool overlap(s16 ax, s16 ay, u8 aa, s16 bx, s16 by, u8 ba)
{
    return ax - ANIM_HB_L[aa] < bx + ANIM_HB_R[ba]
        && bx - ANIM_HB_L[ba] < ax + ANIM_HB_R[aa]
        && ay - ANIM_HB_T[aa] < by + ANIM_HB_B[ba]
        && by - ANIM_HB_T[ba] < ay + ANIM_HB_B[aa];
}

// $A526: boss sweeps X between 0x30 and 0xD0, 1px/frame
static void bossSweep(Obj *o)
{
    if (o->st2 == 0)
    {
        if (--o->x <= 0x30) o->st2 = 1;
    }
    else
    {
        if (++o->x >= 0xD0) o->st2 = 0;
    }
}

static void updateObj(Obj *o)
{
    bool done = animStep(o);
    switch (o->type)
    {
    case 1:                            // shot: rises 4px
        o->y -= 4;
        if (o->y < -8) { shots--; kill(o); return; }
        break;
    case 2:                            // falls 1px
        o->y += 1;
        if (o->y >= 0x100) { kill(o); return; }
        break;
    case 3:                            // falls 2px, oscillates and shoots
        o->y += 2;
        {
            // $A652: chases the player's X via a speed index
            if (px >= o->x) { if (o->st0 < 0x1B) o->st0++; }
            else            { if (o->st0 > -0x1B) o->st0--; }
            s16 v = o->st0;
            s16 w = WOBBLE3[v < 0 ? -v : v];
            o->x += (v < 0) ? -w : w;
            // shoots when aligned (up to 4 shots, every 0x18 frames)
            if (o->st1 < 4 && abs(px - o->x) < 8)
            {
                if (o->st2)
                    o->st2--;
                else
                {
                    o->st2 = 0x18;
                    o->st1++;
                    spawn(10, o->x, o->y);
                }
            }
        }
        if (o->y >= 0x100) { kill(o); return; }
        break;
    case 4:                            // falls 2px zigzagging
        o->y += 2;
        o->x += ZIGZAG4[o->st0];
        o->st0++;
        if (ZIGZAG4[o->st0] == 0 || o->st0 >= (s16) (sizeof(ZIGZAG4) / 2))
            o->st0 = 0;
        if (o->y >= 0x100) { kill(o); return; }
        break;
    case 5:                            // boss ($A355..$A525)
        // st0: 0=flash-in 1=hover 2=wait 3=dive 4=bottom 5=climb
        //      6=dying; st1 = timer/index; st2 = X direction
        switch (o->st0)
        {
        case 0:                        // COLDATA flash + blinks 0x1E frames
            o->st1++;
            SPR_setVisibility(o->spr, (o->st1 & 2) ? HIDDEN : VISIBLE);
            PAL_setPalette(PAL0, (o->st1 & 2)
                           ? GAMEBG_RAW[curBg]->data
                           : GAMEBG[curBg]->palette->data, DMA);
            if (o->st1 >= 0x1E)
            {
                PAL_setPalette(PAL0, GAMEBG[curBg]->palette->data, DMA);
                SPR_setVisibility(o->spr, VISIBLE);
                o->st0 = 1;
            }
            return;
        case 1:                        // hover: ping-pong X 0x30..0xD0
            bossSweep(o);
            if (abs(px - o->x) < 0x18)
            {
                o->st0 = 2;
                o->st1 = 0x1E;
            }
            break;
        case 2:                        // about to dive (keeps sweeping)
            bossSweep(o);
            if (--o->st1 == 0)
            {
                o->st0 = 3;
                o->st1 = 0;
            }
            break;
        case 3:                        // dive along the $A4B7 curve
            o->y += BOSS_DESC[o->st1];
            if (o->st1 < 0x10)
                o->st1++;
            if (o->y >= 0xDC)
            {
                o->y = 0xDC;
                o->st0 = 4;
                o->st1 = 0x3C;
            }
            break;
        case 4:                        // pause at the bottom
            if (--o->st1 == 0)
                o->st0 = 5;
            break;
        case 5:                        // climb back to the hover
            o->y -= 1;
            if (o->y <= 0x80)
            {
                o->y = 0x80;
                o->st0 = 1;
            }
            break;
        case 6:                        // death: blinks 0x78 frames descending
            o->st1++;
            SPR_setVisibility(o->spr, (o->st1 & 1) ? HIDDEN : VISIBLE);
            if (o->st1 & 1)
                o->y += 1;
            if (o->st1 >= 0x78)
            {
                kill(o);
                return;
            }
            break;
        }
        break;
    case 7: case 8:                    // items: fall 1px until 0xE0
        o->y += 1;
        if (o->y >= 0xE0) { kill(o); return; }
        break;
    case 9:                            // vehicle: moves left
        o->x -= 1;
        if (abs(px - o->x) < 0x18)
            o->x -= 3;
        if (o->x < -16) { kill(o); return; }
        break;
    case 10:                           // enemy bullet: falls 3px
        o->y += 3;
        if (o->y >= 0xE0) { kill(o); return; }
        break;
    case 11: case 14:                  // small explosion / fragment
        if (done) { kill(o); return; }
        break;
    case 12:                           // player corpse
        if (done)
        {
            deathTimer = 120;
            kill(o);
            return;
        }
        break;
    case 13:                           // large explosion: emits fragments
        if (o->st0 < 0x18 && !(o->st1 ^= 1))
        {
            spawn(14, o->x + BIGEXP_OFF[o->st0 * 2],
                  o->y + BIGEXP_OFF[o->st0 * 2 + 1]);
            o->st0++;
        }
        if (done && o->st0 >= 0x18) { kill(o); return; }
        break;
    }
    if (o->spr)
        sprCenter(o->spr, ANIM_SPR[o->anim], o->x, o->y);
}

static void collisions(void)
{
    static const u8 COLP[15] = { 0, 0, 1, 1, 1, 4, 0, 2, 3, 1, 1,
                                 0, 0, 0, 0 };        // $AD62
    for (u16 i = 0; i < MAXOBJ; i++)
    {
        Obj *o = &objs[i];
        if (!o->type)
            continue;
        // enemy x player
        u8 h = COLP[o->type];
        if (h && pstate == PSTATE_ALIVE
            && overlap(px, py, panim, o->x, o->y, o->anim))
        {
            // boss only hurts outside flash-in/death ($0ECE)
            if (o->type != 5 || (o->st0 >= 1 && o->st0 <= 5))
                playerHit(h, o);       // 1..4
        }
        // shot x enemy
        if (o->type == 2 || o->type == 3 || o->type == 4
            || o->type == 5 || o->type == 9)
        {
            for (u16 j = 0; j < MAXOBJ; j++)
            {
                Obj *s = &objs[j];
                if (s->type != 1)
                    continue;
                if (overlap(s->x, s->y, s->anim, o->x, o->y, o->anim))
                {
                    shots--;
                    kill(s);
                    shotHit(o);
                    break;
                }
            }
        }
        if (!o->type)
            continue;
    }
}

// ---------------------------------------------------------- one run
void runGame(void)
{
    screenClear();
    curBg = bgRound;
    drawPhoto(GAMEBG[curBg]);
    bgRound = (bgRound + 1) % 6;
    drawText(&txt_hud);
    setPalTarget(PAL1, pal_sprites.data);
    setPalTarget(PAL3, pal_digits.data);
    digitTiles = g_tileNext;
    g_tileNext += ts_digits.numTile;
    VDP_loadTileSet(&ts_digits, digitTiles, DMA);

    memset(objs, 0, sizeof(objs));
    memset(digits, 0, sizeof(digits));
    px = 0x80; py = 0xD8;
    pstate = PSTATE_ALIVE;
    panim = 0x0A;
    shots = kills = 0;
    pending = 0;
    bossActive = FALSE;
    deathTimer = 0;
    spawnDelay = 60;
    seqX = seqT = seq9 = seqDrop = 0;
    pspr = SPR_addSprite(ANIM_SPR[panim], px, py,
                         TILE_ATTR(PAL1, TRUE, FALSE, FALSE));
    sprCenter(pspr, ANIM_SPR[panim], px, py);
    drawDigits();
    SPR_update();
    showFadeIn();

    u16 prev = JOY_readJoypad(JOY_1);
    while (TRUE)
    {
        JOY_update();
        u16 held = JOY_readJoypad(JOY_1);
        u16 pressed = held & ~prev;
        prev = held;

        updatePlayer(held, pressed);
        spawner();
        for (u16 i = 0; i < MAXOBJ; i++)
            if (objs[i].type)
                updateObj(&objs[i]);
        collisions();
        scoreTick();

        if (pstate == PSTATE_DEAD)
        {
            SPR_setVisibility(pspr, HIDDEN);
            if (deathTimer)
            {
                if (--deathTimer == 0)
                    break;             // game over
            }
            // deathTimer==0 with a corpse on screen: wait for it to finish
        }
        SPR_update();
        SYS_doVBlankProcess();
    }
    // release sprites
    SPR_releaseSprite(pspr);
    for (u16 i = 0; i < MAXOBJ; i++)
        if (objs[i].type)
            kill(&objs[i]);
    SPR_update();
    showFadeOut();
}
