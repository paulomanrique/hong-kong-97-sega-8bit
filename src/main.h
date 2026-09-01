#ifndef MAIN_H
#define MAIN_H

#include <genesis.h>
#include "game_tables.h"

extern u16 g_lang;
extern u16 g_tileNext;
extern bool g_cheat;

void screenClear(void);
void setPalTarget(u16 line, const u16 *colors);
void drawPhoto(const Image *img);
void drawText(const Image *img);
bool waitFramesOrButton(u16 frames);
void showFadeIn(void);
void showFadeOut(void);

void runGame(void);

#endif
