/* Frame-driven MIDI plus the title cheat's short buffered PCM phrase. */
#include <string.h>
#include <SMSlib.h>

#include "audio.h"
#include "banked_assets.h"

#define PCM_BUFFER_BYTES 128u
#define MIDI_ATTENUATION 2u

__sfr __at (0x7F) PSGPort;

extern const unsigned char music_psg[];

static const unsigned char *music_cursor;
static unsigned int music_wait;
static unsigned char pcm_buffers[2][PCM_BUFFER_BYTES];
static volatile unsigned char pcm_ready[2], pcm_length[2];
static volatile unsigned char pcm_active, pcm_position, pcm_low_nibble;
static volatile unsigned char pcm_playing, pcm_finished;
static unsigned char pcm_source_exhausted;
static unsigned int pcm_source_offset;

static void music_frame_interrupt(void)
{
    unsigned int delay;
    unsigned char count;

    if (music_wait) {
        --music_wait;
        return;
    }

    for (;;) {
        delay = (unsigned int)music_cursor[0] |
                ((unsigned int)music_cursor[1] << 8);
        count = music_cursor[2];
        music_cursor += 3;
        if (count == 0xFF) {
            music_cursor = music_psg;
            continue;
        }
        while (count--) {
            unsigned char command = *music_cursor++;
            if ((command & 0x90) == 0x90) {
                unsigned char volume = (command & 0x0F) + MIDI_ATTENUATION;
                if (volume > 15) volume = 15;
                command = (command & 0xF0) | volume;
            }
            PSGPort = command;
        }
        music_wait = delay - 1u;
        return;
    }
}

static void cheat_line_interrupt(void)
{
    unsigned char packed, sample, next, volume;

    if (pcm_position >= pcm_length[pcm_active]) {
        pcm_ready[pcm_active] = 0;
        next = pcm_active ^ 1u;
        if (pcm_ready[next]) {
            pcm_active = next;
            pcm_position = 0;
            pcm_low_nibble = 0;
        } else {
            if (pcm_source_exhausted) pcm_finished = 1;
            PSGPort = 0x9F;
            PSGPort = 0xBF;
            PSGPort = 0xDF;
            return;
        }
    }

    packed = pcm_buffers[pcm_active][pcm_position];
    if (pcm_low_nibble) {
        sample = packed & 0x0F;
        pcm_low_nibble = 0;
        ++pcm_position;
    } else {
        sample = packed >> 4;
        pcm_low_nibble = 1;
    }
    volume = 15u - sample;
    /* Drive all three tone channels as one PCM DAC.  A single channel made
       the spoken cheat cue much quieter than the frame-driven MIDI. */
    PSGPort = (unsigned char)(0x90 | volume);
    PSGPort = (unsigned char)(0xB0 | volume);
    PSGPort = (unsigned char)(0xD0 | volume);
}

static void fill_pcm_buffer(unsigned char index)
{
    unsigned int count;
    SMS_saveROMBank();

    if (pcm_source_exhausted) return;
    count = cheat_pcm4_size - pcm_source_offset;
    if (count > PCM_BUFFER_BYTES) count = PCM_BUFFER_BYTES;
    SMS_mapROMBank(cheat_pcm4_bank);
    memcpy(pcm_buffers[index], cheat_pcm4 + pcm_source_offset, count);
    SMS_restoreROMBank();
    pcm_source_offset += count;
    pcm_length[index] = (unsigned char)count;
    if (pcm_source_offset >= cheat_pcm4_size) pcm_source_exhausted = 1;
    pcm_ready[index] = 1;
}

static void restart_midi(void)
{
    PSGPort = 0x9F;
    PSGPort = 0xBF;
    PSGPort = 0xDF;
    PSGPort = 0xFF;
    music_cursor = music_psg;
    music_wait = 0;
    SMS_setFrameInterruptHandler(music_frame_interrupt);
}

void hk_audio_init(void)
{
    pcm_playing = 0;
    restart_midi();
}

void hk_audio_play_cheat(void)
{
    SMS_disableLineInterrupt();
    SMS_setFrameInterruptHandler((void (*)(void))0);
    PSGPort = 0x9F;
    PSGPort = 0xBF;
    PSGPort = 0xDF;
    PSGPort = 0xFF;
    /* Three period-1 carriers give the PCM cue the full PSG output range. */
    PSGPort = 0x81;
    PSGPort = 0x00;
    PSGPort = 0xA1;
    PSGPort = 0x00;
    PSGPort = 0xC1;
    PSGPort = 0x00;

    pcm_ready[0] = pcm_ready[1] = 0;
    pcm_length[0] = pcm_length[1] = 0;
    pcm_source_offset = 0;
    pcm_source_exhausted = 0;
    pcm_finished = 0;
    fill_pcm_buffer(0);
    fill_pcm_buffer(1);
    pcm_active = 0;
    pcm_position = 0;
    pcm_low_nibble = 0;
    pcm_playing = 1;

    SMS_setLineInterruptHandler(cheat_line_interrupt);
    SMS_setLineCounter(1); /* 96 samples/frame = 5,753 Hz NTSC. */
    SMS_enableLineInterrupt();
}

void hk_audio_update(void)
{
    unsigned char index;
    if (!pcm_playing) return;
    if (pcm_finished) {
        hk_audio_stop_cheat();
        return;
    }
    for (index = 0; index != 2; ++index)
        if (!pcm_ready[index] && index != pcm_active)
            fill_pcm_buffer(index);
}

void hk_audio_stop_cheat(void)
{
    if (!pcm_playing) return;
    SMS_disableLineInterrupt();
    pcm_playing = 0;
    pcm_finished = 0;
    restart_midi();
}
