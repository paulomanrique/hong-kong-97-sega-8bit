/* Hong Kong 97 native Sega Master System runtime (SMSlib / SDCC). */
#include <string.h>
#include <SMSlib.h>

#include "main.h"
#include "game.h"
#include "audio.h"
#include "sms_assets.h"
#include "banked_assets.h"

#define NT_VRAM 0x3700u
#define NT_BYTES (32u * 28u * 2u)
#define NT_WRITE(x,y) (0x7700u + ((((u16)(y) << 5) + (x)) << 1))
#define SPRITE_TILE_BASE 256u
#define SPRITE_SOURCE_TILE_CAPACITY 512u
#define SPRITE_CACHE_MISS 0xFFu
#define SPRITE_BANK_SPLIT 128u

extern unsigned char SpriteTableY[64];
extern unsigned char SpriteTableXN[128];
extern unsigned char SpriteNextFree;

static u8 bg_palette[16], sprite_palette[16], flash_palette[16];
static u8 language;
static u16 sprite_cache_source[SMS_SPRITE_CACHE_SIZE];
static u8 sprite_cache_mark[SMS_SPRITE_CACHE_SIZE];
static u8 sprite_cache_slot[SPRITE_SOURCE_TILE_CAPACITY];
static u8 sprite_cache_generation, sprite_cache_victim;

#ifdef HK97_PROFILE
volatile u16 hk_profile_logic_ticks;
volatile u16 hk_profile_render_calls;
volatile u16 hk_profile_cache_misses;
volatile u16 hk_profile_sprite_parts;
#endif

enum ScreenId {
    SCR_LANG,
    SCR_STORY1_L0, SCR_STORY1_L1, SCR_STORY1_L2,
    SCR_STORY2_L0, SCR_STORY2_L1, SCR_STORY2_L2,
    SCR_STORY3_L0, SCR_STORY3_L1, SCR_STORY3_L2,
    SCR_LANG3_1, SCR_LANG3_2,
    SCR_INTRO1,
    SCR_CHEAT,
    SCR_INTRO2_L0, SCR_INTRO2_L1, SCR_INTRO2_L2,
    SCR_INTRO3_L0, SCR_INTRO3_L1, SCR_INTRO3_L2,
    SCR_INTRO4_L0, SCR_INTRO4_L1, SCR_INTRO4_L2,
    SCR_INTRO5_L0, SCR_INTRO5_L1, SCR_INTRO5_L2,
    SCR_GAMEOVER1
};

static u16 rd16(const u8 *p) { return (u16)p[0] | ((u16)p[1] << 8); }

static void copy_banked(void *destination, const u8 *source, u16 size, u8 bank)
{
    SMS_saveROMBank();
    SMS_mapROMBank(bank);
    memcpy(destination, source, size);
    SMS_restoreROMBank();
}

static void copy_banked_to_vram(u16 destination, const u8 *source,
                                u16 size, u8 bank)
{
    SMS_saveROMBank();
    SMS_mapROMBank(bank);
    SMS_VRAMmemcpy(destination, source, size);
    SMS_restoreROMBank();
}

static void hide_physical_sprite_tail(void)
{
    u8 used = SpriteNextFree, i;
    for (i = used; i < 64; ++i) {
        SpriteTableY[i] = 0xE0;
        SpriteTableXN[i * 2] = 0;
        SpriteTableXN[i * 2 + 1] = 0;
    }
    SpriteNextFree = 64;
    SMS_copySpritestoSAT();
    SpriteNextFree = used;
}

static void load_bundle(const u8 *bundle, u8 bank)
{
    u16 tile_count, tiles_offset, tilemap_offset;
    SMS_saveROMBank();
    SMS_mapROMBank(bank);
    tile_count = rd16(bundle + 8);
    tiles_offset = rd16(bundle + 12);
    tilemap_offset = rd16(bundle + 14);
    memcpy(bg_palette, bundle + SMS_BG_CRAM_OFFSET, 16);
    SMS_VRAMmemset(0, 0, NT_VRAM);
    SMS_VRAMmemcpy(0, bundle + tiles_offset, tile_count * 32u);
    SMS_VRAMmemcpy(NT_VRAM, bundle + tilemap_offset, NT_BYTES);
    SMS_restoreROMBank();
}

#define SCREEN_CASE(id, symbol) \
    case id: load_bundle(symbol##_bin, symbol##_bin_bank); break

static void load_screen(enum ScreenId id)
{
    SMS_displayOff();
    switch (id) {
    SCREEN_CASE(SCR_LANG, langselect);
    SCREEN_CASE(SCR_STORY1_L0, story1_l0); SCREEN_CASE(SCR_STORY1_L1, story1_l1); SCREEN_CASE(SCR_STORY1_L2, story1_l2);
    SCREEN_CASE(SCR_STORY2_L0, story2_l0); SCREEN_CASE(SCR_STORY2_L1, story2_l1); SCREEN_CASE(SCR_STORY2_L2, story2_l2);
    SCREEN_CASE(SCR_STORY3_L0, story3_l0); SCREEN_CASE(SCR_STORY3_L1, story3_l1); SCREEN_CASE(SCR_STORY3_L2, story3_l2);
    SCREEN_CASE(SCR_LANG3_1, lang3_1); SCREEN_CASE(SCR_LANG3_2, lang3_2);
    SCREEN_CASE(SCR_INTRO1, intro1);
    SCREEN_CASE(SCR_CHEAT, cheat);
    SCREEN_CASE(SCR_INTRO2_L0, intro2_l0); SCREEN_CASE(SCR_INTRO2_L1, intro2_l1); SCREEN_CASE(SCR_INTRO2_L2, intro2_l2);
    SCREEN_CASE(SCR_INTRO3_L0, intro3_l0); SCREEN_CASE(SCR_INTRO3_L1, intro3_l1); SCREEN_CASE(SCR_INTRO3_L2, intro3_l2);
    SCREEN_CASE(SCR_INTRO4_L0, intro4_l0); SCREEN_CASE(SCR_INTRO4_L1, intro4_l1); SCREEN_CASE(SCR_INTRO4_L2, intro4_l2);
    SCREEN_CASE(SCR_INTRO5_L0, intro5_l0); SCREEN_CASE(SCR_INTRO5_L1, intro5_l1); SCREEN_CASE(SCR_INTRO5_L2, intro5_l2);
    SCREEN_CASE(SCR_GAMEOVER1, gameover1);
    }
    SMS_initSprites();
    hide_physical_sprite_tail();
    SMS_loadBGPalette(bg_palette);
    SMS_displayOn();
}

static u8 scale_color(u8 c, u8 step)
{
    u8 r = c & 3, g = (c >> 2) & 3, b = (c >> 4) & 3;
    r = (u8)((r * step + 7) / 15);
    g = (u8)((g * step + 7) / 15);
    b = (u8)((b * step + 7) / 15);
    return r | (g << 2) | (b << 4);
}

static void fade(u8 fade_in, u8 include_sprites)
{
    u8 step, i, pal[16];
    for (step = 0; step < 15; ++step) {
        u8 level = fade_in ? (u8)(step + 1) : (u8)(14 - step);
        for (i = 0; i < 16; ++i) pal[i] = scale_color(bg_palette[i], level);
        SMS_loadBGPalette(pal);
        if (include_sprites) {
            for (i = 0; i < 16; ++i) pal[i] = scale_color(sprite_palette[i], level);
            SMS_loadSpritePalette(pal);
        }
        SMS_waitForVBlank();
    }
}

static u16 input_mask(void)
{
    u16 keys = SMS_getKeysStatus(), out = 0;
    if (keys & PORT_A_KEY_UP) out |= HK_KEY_UP;
    if (keys & PORT_A_KEY_DOWN) out |= HK_KEY_DOWN;
    if (keys & PORT_A_KEY_LEFT) out |= HK_KEY_LEFT;
    if (keys & PORT_A_KEY_RIGHT) out |= HK_KEY_RIGHT;
    if (keys & PORT_A_KEY_1) out |= HK_KEY_FIRE | HK_KEY_1;
    if (keys & PORT_A_KEY_2) out |= HK_KEY_FIRE | HK_KEY_2;
    return out;
}

static u8 wait_frames_or_button(u16 frames)
{
    u16 previous = input_mask();
    while (frames) {
        u16 now, pressed;
        SMS_waitForVBlank();
        now = input_mask(); pressed = now & ~previous; previous = now;
        if (SMS_queryPauseRequested()) { SMS_resetPauseRequest(); return 1; }
        if (pressed) return 1;
        if (frames != 0xFFFFu) --frames;
    }
    return 0;
}

static u8 language_select(void)
{
    u8 row = 0;
    u16 previous = 0;
    load_screen(SCR_LANG); fade(1, 0);
    for (;;) {
        u16 now, pressed;
        SMS_waitForVBlank(); now = input_mask(); pressed = now & ~previous; previous = now;
        if (pressed & HK_KEY_UP) row = (row + 3) & 3;
        if (pressed & HK_KEY_DOWN) row = (row + 1) & 3;
        if ((pressed & HK_KEY_FIRE) || SMS_queryPauseRequested()) break;
    }
    SMS_resetPauseRequest(); fade(0, 0); return row;
}

static void title_sequence(void)
{
    u8 page, row = language_select();
    if (row == 3) {
        load_screen(SCR_LANG3_1); fade(1,0); wait_frames_or_button(0xFFFF); fade(0,0);
        load_screen(SCR_LANG3_2); fade(1,0); wait_frames_or_button(0xFFFF); fade(0,0);
        row = 0;
    }
    language = row;
    for (page = 0; page < 3; ++page) {
        load_screen((enum ScreenId)(SCR_STORY1_L0 + page * 3 + language));
        fade(1,0); wait_frames_or_button(0xFFFF); fade(0,0);
    }
}

static void intro_pages(void)
{
    static const u16 konami[10] = {
        HK_KEY_UP, HK_KEY_UP, HK_KEY_DOWN, HK_KEY_DOWN,
        HK_KEY_LEFT, HK_KEY_RIGHT, HK_KEY_LEFT, HK_KEY_RIGHT,
        HK_KEY_2, HK_KEY_1,
    };
    u8 page, manual = 0, kstep = 0;

title_rebuild:
    load_screen(SCR_INTRO1);
    fade(1, 0);
    {
        u16 previous = input_mask();
        for (;;) {
            u16 now, pressed;
            SMS_waitForVBlank();
            now = input_mask();
            pressed = now & ~previous;
            previous = now;

            if (pressed) {
                if (pressed & konami[kstep]) {
                    if (++kstep == 10) {
                        u16 egg_previous;
                        kstep = 0;
                        hk_game_set_cheat(1);
                        fade(0, 0);
                        load_screen(SCR_CHEAT);
                        fade(1, 0);
                        hk_audio_play_cheat();
                        egg_previous = input_mask();
                        for (;;) {
                            u16 egg_now, egg_pressed;
                            SMS_waitForVBlank();
                            hk_audio_update();
                            egg_now = input_mask();
                            egg_pressed = egg_now & ~egg_previous;
                            egg_previous = egg_now;
                            if (SMS_queryPauseRequested()) {
                                SMS_resetPauseRequest();
                                break;
                            }
                            if (egg_pressed & (HK_KEY_1 | HK_KEY_2)) break;
                        }
                        hk_audio_stop_cheat();
                        fade(0, 0);
                        goto title_rebuild;
                    }
                } else {
                    kstep = (pressed & HK_KEY_UP) ? 1 : 0;
                }
            }

            /* SMS Pause is the controller's Start equivalent. No face button
             * advances this first presentation screen. */
            if (SMS_queryPauseRequested()) {
                SMS_resetPauseRequest();
                break;
            }
        }
    }
    fade(0, 0);
    for (page = 0; page < 4; ++page) {
        load_screen((enum ScreenId)(SCR_INTRO2_L0 + page * 3 + language));
        fade(1,0);
        if (wait_frames_or_button(manual ? 0xFFFFu : 240u)) manual = 1;
        fade(0,0);
    }
}

static void game_over_screens(void)
{
    load_screen(SCR_GAMEOVER1);
    fade(1,0); wait_frames_or_button(0xFFFF); fade(0,0);
}

static void load_game_background(u8 index)
{
    SMS_displayOff();
#ifdef HK97_BLANK_GAME_BG
    (void)index;
    copy_banked(bg_palette, gamebg0_bin + SMS_BG_CRAM_OFFSET, 16,
                gamebg0_bin_bank);
    memcpy(flash_palette, bg_palette, 16);
    SMS_VRAMmemset(0, 0, NT_VRAM);
    SMS_VRAMmemset(NT_VRAM, 0, NT_BYTES);
#else
    switch (index) {
    case 0:
        load_bundle(gamebg0_bin, gamebg0_bin_bank);
        copy_banked(flash_palette, gamebg0_flash_cram, 16, gamebg0_flash_cram_bank);
        break;
    case 1:
        load_bundle(gamebg1_bin, gamebg1_bin_bank);
        copy_banked(flash_palette, gamebg1_flash_cram, 16, gamebg1_flash_cram_bank);
        break;
    case 2:
        load_bundle(gamebg2_bin, gamebg2_bin_bank);
        copy_banked(flash_palette, gamebg2_flash_cram, 16, gamebg2_flash_cram_bank);
        break;
    case 3:
        load_bundle(gamebg3_bin, gamebg3_bin_bank);
        copy_banked(flash_palette, gamebg3_flash_cram, 16, gamebg3_flash_cram_bank);
        break;
    case 4:
        load_bundle(gamebg4_bin, gamebg4_bin_bank);
        copy_banked(flash_palette, gamebg4_flash_cram, 16, gamebg4_flash_cram_bank);
        break;
    default:
        load_bundle(gamebg5_bin, gamebg5_bin_bank);
        copy_banked(flash_palette, gamebg5_flash_cram, 16, gamebg5_flash_cram_bank);
        break;
    }
#endif
    copy_banked(sprite_palette, sprites_cram, 16, sprites_cram_bank);
    copy_banked_to_vram(SPRITE_TILE_BASE * 32u, sprites_seed_tiles,
                        sprites_seed_tiles_size, sprites_seed_tiles_bank);
    {
        u16 i;
        memset(sprite_cache_slot, SPRITE_CACHE_MISS,
               sizeof(sprite_cache_slot));
        for (i = 0; i < SMS_SPRITE_CACHE_SIZE; ++i) {
            sprite_cache_source[i] = sms_sprite_cache_seed[i];
            sprite_cache_mark[i] = 0;
            sprite_cache_slot[sms_sprite_cache_seed[i]] = (u8)i;
        }
    }
    sprite_cache_generation = 0;
    sprite_cache_victim = 0;
    SMS_loadBGPalette(bg_palette); SMS_loadSpritePalette(sprite_palette);
    SMS_initSprites(); hide_physical_sprite_tail(); SMS_displayOn();
}

static const SmsSpriteFrame *sprite_frame(u8 anim, u8 frame)
{
    u8 count = sms_anim_frame_count[anim];
    if (!count) return 0;
    if (frame >= count) frame = 0;
    return &sms_sprite_frames[sms_anim_first_frame[anim] + frame];
}

static u8 load_sprite_tile(u16 source)
{
    u16 i;
    u8 slot;
    for (i = 0; i < SMS_SPRITE_CACHE_SIZE; ++i) {
        slot = sprite_cache_victim;
        if (++sprite_cache_victim >= SMS_SPRITE_CACHE_SIZE)
            sprite_cache_victim = 0;
        if (sprite_cache_mark[slot] != sprite_cache_generation) {
            const u8 *source_bytes;
#ifdef HK97_PROFILE
            ++hk_profile_cache_misses;
#endif
            sprite_cache_slot[sprite_cache_source[slot]] = SPRITE_CACHE_MISS;
            if (source < SPRITE_BANK_SPLIT) {
                SMS_mapROMBank(sprites0_tiles_bank);
                source_bytes = sprites0_tiles + source * 64u;
            } else {
                SMS_mapROMBank(sprites1_tiles_bank);
                source_bytes = sprites1_tiles +
                               (source - SPRITE_BANK_SPLIT) * 64u;
            }
            SMS_VRAMmemcpy((SPRITE_TILE_BASE + slot * 2u) * 32u,
                           source_bytes, 64);
            sprite_cache_source[slot] = source;
            sprite_cache_slot[source] = slot;
            sprite_cache_mark[slot] = sprite_cache_generation;
            return (u8)(slot * 2u);
        }
    }
    return 0; /* A frame can reference at most the 64 physical SAT entries. */
}

static void add_metasprite(u8 anim, u8 frame, s16 x, s16 y)
{
    const SmsSpriteFrame *f = sprite_frame(anim, frame);
    const SmsSpritePart *p;
    u8 remaining;
    if (!f) return;
    p = &sms_sprite_parts[f->first_part];
    remaining = f->part_count;
    while (remaining--) {
        s16 sx = x + p->dx, sy = y + p->dy;
        u8 slot, tile;
#ifdef HK97_PROFILE
        ++hk_profile_sprite_parts;
#endif
        if (SpriteNextFree >= 64) return;
        if (sx < 0 || sx > 255 || sy < -15 || sy > 191) { ++p; continue; }
        slot = sprite_cache_slot[p->tile];
        if (slot == SPRITE_CACHE_MISS) tile = load_sprite_tile(p->tile);
        else {
            sprite_cache_mark[slot] = sprite_cache_generation;
            tile = (u8)(slot * 2u);
        }
        slot = SpriteNextFree++;
        SpriteTableY[slot] = (u8)(sy - 1);
        SpriteTableXN[slot * 2] = (u8)sx;
        SpriteTableXN[slot * 2 + 1] = tile;
        ++p;
    }
}

static void render_game(void)
{
    HKObject *o;
#ifdef HK97_PROFILE
    ++hk_profile_render_calls;
#endif
    if (++sprite_cache_generation == 0) {
        memset(sprite_cache_mark, 0, sizeof(sprite_cache_mark));
        sprite_cache_generation = 1;
    }
    SMS_initSprites();
    SMS_saveROMBank();
    if (hk_player_visible) add_metasprite(hk_player_anim,0,hk_player_x,hk_player_y);
    for (o=hk_objects;o!=hk_objects+HK_MAX_OBJECTS;++o) if (o->type==5 && o->visible)
        add_metasprite(o->anim,o->frame,o->x,o->y);
    /* Effects and the corpse must survive SAT pressure: render them before
     * ordinary enemies, shots and drops. */
    for (o=hk_objects;o!=hk_objects+HK_MAX_OBJECTS;++o) if (o->type>=11 && o->visible)
        add_metasprite(o->anim,o->frame,o->x,o->y);
    for (o=hk_objects;o!=hk_objects+HK_MAX_OBJECTS;++o) if (o->type && o->type<11 && o->type!=5 && o->visible)
        add_metasprite(o->anim,o->frame,o->x,o->y);
    SMS_restoreROMBank();
#ifndef HK97_NO_SAT_COPY
    hide_physical_sprite_tail();
#endif
}

static void run_game(void)
{
    u16 previous = 0;
    u8 old_flash = 0;
    hk_game_begin(); load_game_background(hk_current_background); fade(1,1);
#ifdef HK97_PROFILE
    hk_profile_logic_ticks = 0;
    hk_profile_render_calls = 0;
    hk_profile_cache_misses = 0;
    hk_profile_sprite_parts = 0;
#endif
    for (;;) {
        u16 now, pressed;
        SMS_waitForVBlank(); now=input_mask(); pressed=now & ~previous; previous=now;
        if (hk_game_step(now,pressed)) break;
#ifdef HK97_PROFILE
        ++hk_profile_logic_ticks;
#endif
        if (hk_background_flash != old_flash) {
            SMS_loadBGPalette(hk_background_flash ? flash_palette : bg_palette);
            old_flash = hk_background_flash;
        }
#ifndef HK97_NO_RENDER
        render_game();
#endif
    }
    fade(0,1);
}

void main(void)
{
    /* These live in different VDP registers and cannot be ORed together. */
    SMS_VDPturnOnFeature(VDPFEATURE_EXTRAHEIGHT);
    SMS_VDPturnOnFeature(VDPFEATURE_224LINES);
    SMS_useFirstHalfTilesforSprites(0);
    SMS_setSpriteMode(SPRITEMODE_TALL);
    SMS_displayOff(); SMS_VRAMmemset(0,0,0x4000); SMS_displayOn();
    hk_audio_init();
    language = 2; /* English, matching the original menu's third row. */
    for (;;) { intro_pages(); run_game(); game_over_screens(); }
}

SMS_EMBED_SEGA_ROM_HEADER(0x0000, 0);
SMS_EMBED_SDSC_HEADER_AUTO_DATE(0, 1, "Paulo Manrique",
                                "Hong Kong 97 SMS", "Native port");
