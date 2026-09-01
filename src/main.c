// Hong Kong 97 — Mega Drive port (SGDK), reimplemented from the SNES
// ROM disassembly (docs/mapping.md and disasm/hk97_trace.asm).
//
// Original flow: RESET -> title/language/story (once) ->
//   loop { intro pages -> gameplay -> game over }.
// Video: H32 (256x224), photo on plane B (PAL0), text on plane A (PAL2),
// sprites PAL1, HUD/digits PAL3.
#include <genesis.h>
#include "resources.h"
#include "main.h"

u16 g_lang;                       // 0=ja 1=zh 2=en (3=CM -> extra screens)
bool g_cheat;                     // cheat mode (Konami code)

u16 g_tileNext;                   // sequential VRAM tile allocator
u16 g_palTarget[64];              // target palettes: applied only on fade-in
                                  // (screen stays black while loading)

void screenClear(void)
{
    VDP_clearPlane(BG_A, TRUE);
    VDP_clearPlane(BG_B, TRUE);
    // base 16 (we don't use the system font): full photos reach ~896
    // tiles and must fit before the sprite engine's region
    g_tileNext = 16;
    memset(g_palTarget, 0, sizeof(g_palTarget));
}

void setPalTarget(u16 line, const u16 *colors)
{
    memcpy(&g_palTarget[line * 16], colors, 16 * sizeof(u16));
}

void drawPhoto(const Image *img)
{
    setPalTarget(PAL0, img->palette->data);
    VDP_drawImageEx(BG_B, img, TILE_ATTR_FULL(PAL0, FALSE, FALSE, FALSE,
                                              g_tileNext), 0, 0, FALSE, TRUE);
    g_tileNext += img->tileset->numTile;
}

void drawText(const Image *img)
{
    setPalTarget(PAL2, img->palette->data);
    VDP_drawImageEx(BG_A, img, TILE_ATTR_FULL(PAL2, TRUE, FALSE, FALSE,
                                              g_tileNext), 0, 0, FALSE, TRUE);
    g_tileNext += img->tileset->numTile;
}

// $C8E3: wait N frames or a button (0xFFFF = button only). TRUE if button.
bool waitFramesOrButton(u16 frames)
{
    JOY_update();
    u16 prev = JOY_readJoypad(JOY_1);
    while (frames)
    {
        SYS_doVBlankProcess();
        JOY_update();
        u16 now = JOY_readJoypad(JOY_1);
        u16 pressed = now & ~prev;
        prev = now;
        if (pressed & (BUTTON_A | BUTTON_B | BUTTON_C | BUTTON_START))
            return TRUE;
        if (frames != 0xFFFF)
            frames--;
    }
    return FALSE;
}

// apply the target palettes with a fade-in from black
void showFadeIn(void)
{
    u16 black[64];
    memset(black, 0, sizeof(black));
    PAL_setColors(0, black, 64, CPU);
    PAL_fadeIn(0, 63, g_palTarget, 15, FALSE);
}

void showFadeOut(void)
{
    PAL_fadeOut(0, 63, 15, FALSE);
}

// -------------------------------------------------- title / language
static const Image *const STORY_TXT[3][3] = {
    { &txt_s1_l0, &txt_s2_l0, &txt_s3_l0 },
    { &txt_s1_l1, &txt_s2_l1, &txt_s3_l1 },
    { &txt_s1_l2, &txt_s2_l2, &txt_s3_l2 },
};

static void showLang3Screens(void)
{
    static const Image *const ph[2] = { &img_lang3a, &img_lang3b };
    static const Image *const tx[2] = { &txt_lang3a, &txt_lang3b };
    for (u16 i = 0; i < 2; i++)
    {
        screenClear();
        drawPhoto(ph[i]);
        drawText(tx[i]);
        showFadeIn();
        waitFramesOrButton(0xFFFF);
        showFadeOut();
    }
}

// ------------------------------------------ cheat mode (easter egg)
// Konami code on the title screen (HK97/(C)1995 card, the 1st intro
// page): avatar + channel logo + jingle, and turns on the cheats
// (invincible + turbo while holding A).
static const u16 KONAMI[10] = {
    BUTTON_UP, BUTTON_UP, BUTTON_DOWN, BUTTON_DOWN, BUTTON_LEFT,
    BUTTON_RIGHT, BUTTON_LEFT, BUTTON_RIGHT, BUTTON_B, BUTTON_A
};

static void showEggScreen(void)
{
    SND_PCM_stopPlay();
    screenClear();
    setPalTarget(PAL0, img_egg_avatar.palette->data);
    VDP_drawImageEx(BG_B, &img_egg_avatar,
                    TILE_ATTR_FULL(PAL0, FALSE, FALSE, FALSE, g_tileNext),
                    8, 6, FALSE, TRUE);          // 128x128 centered
    g_tileNext += img_egg_avatar.tileset->numTile;
    drawText(&img_egg_txt);
    showFadeIn();
    SND_PCM_startPlay(snd_egg, sizeof(snd_egg),
                      SOUND_PCM_RATE_8000, SOUND_PAN_CENTER, FALSE);
    u16 prev = JOY_readJoypad(JOY_1);
    bool musicBack = FALSE;
    while (TRUE)
    {
        SYS_doVBlankProcess();
        JOY_update();
        u16 now = JOY_readJoypad(JOY_1);
        u16 pr = now & ~prev;
        prev = now;
        if (!musicBack && !SND_PCM_isPlaying())
        {
            SND_PCM_startPlay(snd_music, sizeof(snd_music),
                              SOUND_PCM_RATE_8000, SOUND_PAN_CENTER, TRUE);
            musicBack = TRUE;
        }
        if (pr & (BUTTON_A | BUTTON_B | BUTTON_C | BUTTON_START))
            break;
    }
    if (!musicBack)
        SND_PCM_startPlay(snd_music, sizeof(snd_music),
                          SOUND_PCM_RATE_8000, SOUND_PAN_CENTER, TRUE);
    showFadeOut();
}

static u16 languageSelect(void)
{
    // MENU_CURSOR ($BD01): [?, n, X,Y0, X,Y1, X,Y2, X,Y3]
    Sprite *cur;
    s16 row = 0;

    screenClear();
    drawText(&txt_lang);
    setPalTarget(PAL1, pal_sprites.data);
    cur = SPR_addSprite(&spr_a0D, MENU_CURSOR[2] - 8,
                        MENU_CURSOR[3 + row * 2] - 8,
                        TILE_ATTR(PAL1, TRUE, FALSE, FALSE));
    SPR_update();
    showFadeIn();
    u16 prev = JOY_readJoypad(JOY_1);
    u16 animT = 0, animF = 0;
    while (TRUE)
    {
        JOY_update();
        u16 now = JOY_readJoypad(JOY_1);
        u16 pressed = now & ~prev;
        prev = now;
        if (pressed & BUTTON_UP)    row = (row + 3) & 3;
        if (pressed & BUTTON_DOWN)  row = (row + 1) & 3;
        if (pressed & (BUTTON_A | BUTTON_B | BUTTON_C | BUTTON_START))
            break;
        SPR_setPosition(cur, MENU_CURSOR[2] - 8,
                        MENU_CURSOR[3 + row * 2] - 8);
        if (++animT >= 8) { animT = 0; animF ^= 1; SPR_setFrame(cur, animF); }
        SPR_update();
        SYS_doVBlankProcess();
    }
    SPR_releaseSprite(cur);
    SPR_update();
    showFadeOut();
    return row;
}

// title screen (HK97 card): blinking PRESS START, only Start advances,
// and the Konami code turns on the cheat mode
static void titleScreen(const Image *photo, const Image *txt)
{
    u16 kstep = 0;

rebuild:
    screenClear();
    drawPhoto(photo);
    drawText(txt);
    setPalTarget(PAL3, img_pstart.palette->data);
    u16 psTiles = g_tileNext;
    u16 psW = img_pstart.tilemap->w;
    u16 psX = (32 - psW) / 2;
    VDP_drawImageEx(BG_A, &img_pstart,
                    TILE_ATTR_FULL(PAL3, TRUE, FALSE, FALSE, psTiles),
                    psX, 26, FALSE, TRUE);
    g_tileNext += img_pstart.tileset->numTile;
    showFadeIn();
    u16 prev = JOY_readJoypad(JOY_1);
    u16 blink = 0;
    while (TRUE)
    {
        JOY_update();
        u16 now = JOY_readJoypad(JOY_1);
        u16 pressed = now & ~prev;
        prev = now;
        // Konami code progress
        if (pressed)
        {
            if (pressed & KONAMI[kstep])
            {
                kstep++;
                if (kstep == 10)
                {
                    kstep = 0;
                    g_cheat = TRUE;
                    showFadeOut();
                    showEggScreen();
                    goto rebuild;
                }
            }
            else
                kstep = (pressed & BUTTON_UP) ? 1 : 0;
        }
        if (pressed & BUTTON_START)
            break;
        // blink PRESS START every 32 frames
        blink++;
        if ((blink & 31) == 0)
        {
            if (blink & 32)
                VDP_clearTileMapRect(BG_A, psX, 26, psW, 2);
            else
                VDP_drawImageEx(BG_A, &img_pstart,
                                TILE_ATTR_FULL(PAL3, TRUE, FALSE, FALSE,
                                               psTiles), psX, 26, FALSE,
                                TRUE);
        }
        SYS_doVBlankProcess();
    }
    showFadeOut();
}

static void titleSequence(void)
{
    u16 row = languageSelect();
    if (row == 3)                      // "CM": extra screens, falls to ja
    {
        showLang3Screens();
        row = 0;
    }
    g_lang = row;
    // 3 story pages (plain text, advances with a button)
    for (u16 p = 0; p < 3; p++)
    {
        screenClear();
        drawText(STORY_TXT[g_lang][p]);
        showFadeIn();
        waitFramesOrButton(0xFFFF);
        showFadeOut();
    }
}

// -------------------------------------------------- intro pages
static void introPages(void)
{
    static const Image *const photos[5] = {
        &img_intro1, &img_intro2, &img_intro3, &img_intro4, &img_intro5
    };
    const Image *const txts[5][3] = {
        { &txt_i1, &txt_i1, &txt_i1 },
        { &txt_i2_l0, &txt_i2_l1, &txt_i2_l2 },
        { &txt_i3_l0, &txt_i3_l1, &txt_i3_l2 },
        { &txt_i4_l0, &txt_i4_l1, &txt_i4_l2 },
        { &txt_i5_l0, &txt_i5_l1, &txt_i5_l2 },
    };
    // page 1 = title screen: PRESS START + Konami code (cheat); the
    // others advance with a button or 240 frames (manual mode, $C0BF)
    titleScreen(photos[0], txts[0][g_lang]);
    bool manual = FALSE;
    for (u16 p = 1; p < 5; p++)
    {
        screenClear();
        drawPhoto(photos[p]);
        drawText(txts[p][g_lang]);
        showFadeIn();
        u16 wait = manual ? 0xFFFF : 240;
        if (waitFramesOrButton(wait))
            manual = TRUE;
        showFadeOut();
    }
}

// -------------------------------------------------- game over
static void gameOverScreens(void)
{
    screenClear();
    drawPhoto(&img_gover);
    drawText(&txt_gover1);
    showFadeIn();
    waitFramesOrButton(0xFFFF);
    showFadeOut();
    static const Image *const tx[2] = { &txt_gover2, &txt_gover3 };
    for (u16 i = 0; i < 2; i++)
    {
        screenClear();
        drawText(tx[i]);
        showFadeIn();
        waitFramesOrButton(0xFFFF);
        showFadeOut();
    }
}

int main(bool hard)
{
    (void) hard;
    VDP_setScreenWidth256();
    VDP_setScreenHeight224();
    SPR_init();
    JOY_init();

    // music: the game's only audio, infinite loop from boot
    SND_PCM_loadDriver(TRUE);
    SND_PCM_startPlay(snd_music, sizeof(snd_music), SOUND_PCM_RATE_8000,
                      SOUND_PAN_CENTER, TRUE);

    titleSequence();
    while (TRUE)
    {
        introPages();
        runGame();
        gameOverScreens();
    }
    return 0;
}
