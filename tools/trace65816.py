#!/usr/bin/env python3
"""Recursive-descent 65816 disassembler for the Hong Kong 97 LoROM.

Walks the code from the vectors (RESET/NMI/IRQ), tracking the M/X flags
(REP/SEP) to size immediates. Anything not reached is treated as data. It
annotates PPU/CPU registers ($21xx/$42xx/$43xx) to make DMAs easier to find
(the source of tiles/palettes in the ROM).

Usage: python tools/trace65816.py work/hk97.sfc -o disasm/hk97_trace.asm
"""
import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------- mapping

def lorom_to_file(addr24: int) -> int | None:
    """SNES address (bank<<16|addr) -> file offset, or None if out of range."""
    bank = (addr24 >> 16) & 0xFF
    addr = addr24 & 0xFFFF
    b = bank & 0x7F
    if b <= 0x3F and addr < 0x8000:
        return None  # RAM / registradores
    if addr < 0x8000:
        return None
    off = b * 0x8000 + (addr - 0x8000)
    return off


# ------------------------------------------------------------ tabela opcodes
# (mnemonico, modo). Tamanho decidido pelo modo; immM/immX dependem das flags.
OPCODES = {
    0x00: ("BRK", "imm8"), 0x01: ("ORA", "idpx"), 0x02: ("COP", "imm8"),
    0x03: ("ORA", "sr"), 0x04: ("TSB", "dp"), 0x05: ("ORA", "dp"),
    0x06: ("ASL", "dp"), 0x07: ("ORA", "idlp"), 0x08: ("PHP", "imp"),
    0x09: ("ORA", "immM"), 0x0A: ("ASL", "acc"), 0x0B: ("PHD", "imp"),
    0x0C: ("TSB", "abs"), 0x0D: ("ORA", "abs"), 0x0E: ("ASL", "abs"),
    0x0F: ("ORA", "abl"),
    0x10: ("BPL", "rel8"), 0x11: ("ORA", "idpy"), 0x12: ("ORA", "idp"),
    0x13: ("ORA", "isry"), 0x14: ("TRB", "dp"), 0x15: ("ORA", "dpx"),
    0x16: ("ASL", "dpx"), 0x17: ("ORA", "idly"), 0x18: ("CLC", "imp"),
    0x19: ("ORA", "absy"), 0x1A: ("INC", "acc"), 0x1B: ("TCS", "imp"),
    0x1C: ("TRB", "abs"), 0x1D: ("ORA", "absx"), 0x1E: ("ASL", "absx"),
    0x1F: ("ORA", "ablx"),
    0x20: ("JSR", "abs"), 0x21: ("AND", "idpx"), 0x22: ("JSL", "abl"),
    0x23: ("AND", "sr"), 0x24: ("BIT", "dp"), 0x25: ("AND", "dp"),
    0x26: ("ROL", "dp"), 0x27: ("AND", "idlp"), 0x28: ("PLP", "imp"),
    0x29: ("AND", "immM"), 0x2A: ("ROL", "acc"), 0x2B: ("PLD", "imp"),
    0x2C: ("BIT", "abs"), 0x2D: ("AND", "abs"), 0x2E: ("ROL", "abs"),
    0x2F: ("AND", "abl"),
    0x30: ("BMI", "rel8"), 0x31: ("AND", "idpy"), 0x32: ("AND", "idp"),
    0x33: ("AND", "isry"), 0x34: ("BIT", "dpx"), 0x35: ("AND", "dpx"),
    0x36: ("ROL", "dpx"), 0x37: ("AND", "idly"), 0x38: ("SEC", "imp"),
    0x39: ("AND", "absy"), 0x3A: ("DEC", "acc"), 0x3B: ("TSC", "imp"),
    0x3C: ("BIT", "absx"), 0x3D: ("AND", "absx"), 0x3E: ("ROL", "absx"),
    0x3F: ("AND", "ablx"),
    0x40: ("RTI", "imp"), 0x41: ("EOR", "idpx"), 0x42: ("WDM", "imm8"),
    0x43: ("EOR", "sr"), 0x44: ("MVP", "bm"), 0x45: ("EOR", "dp"),
    0x46: ("LSR", "dp"), 0x47: ("EOR", "idlp"), 0x48: ("PHA", "imp"),
    0x49: ("EOR", "immM"), 0x4A: ("LSR", "acc"), 0x4B: ("PHK", "imp"),
    0x4C: ("JMP", "abs"), 0x4D: ("EOR", "abs"), 0x4E: ("LSR", "abs"),
    0x4F: ("EOR", "abl"),
    0x50: ("BVC", "rel8"), 0x51: ("EOR", "idpy"), 0x52: ("EOR", "idp"),
    0x53: ("EOR", "isry"), 0x54: ("MVN", "bm"), 0x55: ("EOR", "dpx"),
    0x56: ("LSR", "dpx"), 0x57: ("EOR", "idly"), 0x58: ("CLI", "imp"),
    0x59: ("EOR", "absy"), 0x5A: ("PHY", "imp"), 0x5B: ("TCD", "imp"),
    0x5C: ("JML", "abl"), 0x5D: ("EOR", "absx"), 0x5E: ("LSR", "absx"),
    0x5F: ("EOR", "ablx"),
    0x60: ("RTS", "imp"), 0x61: ("ADC", "idpx"), 0x62: ("PER", "rel16"),
    0x63: ("ADC", "sr"), 0x64: ("STZ", "dp"), 0x65: ("ADC", "dp"),
    0x66: ("ROR", "dp"), 0x67: ("ADC", "idlp"), 0x68: ("PLA", "imp"),
    0x69: ("ADC", "immM"), 0x6A: ("ROR", "acc"), 0x6B: ("RTL", "imp"),
    0x6C: ("JMP", "ind"), 0x6D: ("ADC", "abs"), 0x6E: ("ROR", "abs"),
    0x6F: ("ADC", "abl"),
    0x70: ("BVS", "rel8"), 0x71: ("ADC", "idpy"), 0x72: ("ADC", "idp"),
    0x73: ("ADC", "isry"), 0x74: ("STZ", "dpx"), 0x75: ("ADC", "dpx"),
    0x76: ("ROR", "dpx"), 0x77: ("ADC", "idly"), 0x78: ("SEI", "imp"),
    0x79: ("ADC", "absy"), 0x7A: ("PLY", "imp"), 0x7B: ("TDC", "imp"),
    0x7C: ("JMP", "iax"), 0x7D: ("ADC", "absx"), 0x7E: ("ROR", "absx"),
    0x7F: ("ADC", "ablx"),
    0x80: ("BRA", "rel8"), 0x81: ("STA", "idpx"), 0x82: ("BRL", "rel16"),
    0x83: ("STA", "sr"), 0x84: ("STY", "dp"), 0x85: ("STA", "dp"),
    0x86: ("STX", "dp"), 0x87: ("STA", "idlp"), 0x88: ("DEY", "imp"),
    0x89: ("BIT", "immM"), 0x8A: ("TXA", "imp"), 0x8B: ("PHB", "imp"),
    0x8C: ("STY", "abs"), 0x8D: ("STA", "abs"), 0x8E: ("STX", "abs"),
    0x8F: ("STA", "abl"),
    0x90: ("BCC", "rel8"), 0x91: ("STA", "idpy"), 0x92: ("STA", "idp"),
    0x93: ("STA", "isry"), 0x94: ("STY", "dpx"), 0x95: ("STA", "dpx"),
    0x96: ("STX", "dpy"), 0x97: ("STA", "idly"), 0x98: ("TYA", "imp"),
    0x99: ("STA", "absy"), 0x9A: ("TXS", "imp"), 0x9B: ("TXY", "imp"),
    0x9C: ("STZ", "abs"), 0x9D: ("STA", "absx"), 0x9E: ("STZ", "absx"),
    0x9F: ("STA", "ablx"),
    0xA0: ("LDY", "immX"), 0xA1: ("LDA", "idpx"), 0xA2: ("LDX", "immX"),
    0xA3: ("LDA", "sr"), 0xA4: ("LDY", "dp"), 0xA5: ("LDA", "dp"),
    0xA6: ("LDX", "dp"), 0xA7: ("LDA", "idlp"), 0xA8: ("TAY", "imp"),
    0xA9: ("LDA", "immM"), 0xAA: ("TAX", "imp"), 0xAB: ("PLB", "imp"),
    0xAC: ("LDY", "abs"), 0xAD: ("LDA", "abs"), 0xAE: ("LDX", "abs"),
    0xAF: ("LDA", "abl"),
    0xB0: ("BCS", "rel8"), 0xB1: ("LDA", "idpy"), 0xB2: ("LDA", "idp"),
    0xB3: ("LDA", "isry"), 0xB4: ("LDY", "dpx"), 0xB5: ("LDA", "dpx"),
    0xB6: ("LDX", "dpy"), 0xB7: ("LDA", "idly"), 0xB8: ("CLV", "imp"),
    0xB9: ("LDA", "absy"), 0xBA: ("TSX", "imp"), 0xBB: ("TYX", "imp"),
    0xBC: ("LDY", "absx"), 0xBD: ("LDA", "absx"), 0xBE: ("LDX", "absy"),
    0xBF: ("LDA", "ablx"),
    0xC0: ("CPY", "immX"), 0xC1: ("CMP", "idpx"), 0xC2: ("REP", "imm8"),
    0xC3: ("CMP", "sr"), 0xC4: ("CPY", "dp"), 0xC5: ("CMP", "dp"),
    0xC6: ("DEC", "dp"), 0xC7: ("CMP", "idlp"), 0xC8: ("INY", "imp"),
    0xC9: ("CMP", "immM"), 0xCA: ("DEX", "imp"), 0xCB: ("WAI", "imp"),
    0xCC: ("CPY", "abs"), 0xCD: ("CMP", "abs"), 0xCE: ("DEC", "abs"),
    0xCF: ("CMP", "abl"),
    0xD0: ("BNE", "rel8"), 0xD1: ("CMP", "idpy"), 0xD2: ("CMP", "idp"),
    0xD3: ("CMP", "isry"), 0xD4: ("PEI", "dp"), 0xD5: ("CMP", "dpx"),
    0xD6: ("DEC", "dpx"), 0xD7: ("CMP", "idly"), 0xD8: ("CLD", "imp"),
    0xD9: ("CMP", "absy"), 0xDA: ("PHX", "imp"), 0xDB: ("STP", "imp"),
    0xDC: ("JML", "ial"), 0xDD: ("CMP", "absx"), 0xDE: ("DEC", "absx"),
    0xDF: ("CMP", "ablx"),
    0xE0: ("CPX", "immX"), 0xE1: ("SBC", "idpx"), 0xE2: ("SEP", "imm8"),
    0xE3: ("SBC", "sr"), 0xE4: ("CPX", "dp"), 0xE5: ("SBC", "dp"),
    0xE6: ("INC", "dp"), 0xE7: ("SBC", "idlp"), 0xE8: ("INX", "imp"),
    0xE9: ("SBC", "immM"), 0xEA: ("NOP", "imp"), 0xEB: ("XBA", "imp"),
    0xEC: ("CPX", "abs"), 0xED: ("SBC", "abs"), 0xEE: ("INC", "abs"),
    0xEF: ("SBC", "abl"),
    0xF0: ("BEQ", "rel8"), 0xF1: ("SBC", "idpy"), 0xF2: ("SBC", "idp"),
    0xF3: ("SBC", "isry"), 0xF4: ("PEA", "abs"), 0xF5: ("SBC", "dpx"),
    0xF6: ("INC", "dpx"), 0xF7: ("SBC", "idly"), 0xF8: ("SED", "imp"),
    0xF9: ("SBC", "absy"), 0xFA: ("PLX", "imp"), 0xFB: ("XCE", "imp"),
    0xFC: ("JSR", "iax"), 0xFD: ("SBC", "absx"), 0xFE: ("INC", "absx"),
    0xFF: ("SBC", "ablx"),
}

MODE_LEN = {
    "imp": 1, "acc": 1, "imm8": 2, "dp": 2, "dpx": 2, "dpy": 2, "idp": 2,
    "idpx": 2, "idpy": 2, "idlp": 2, "idly": 2, "sr": 2, "isry": 2,
    "rel8": 2, "abs": 3, "absx": 3, "absy": 3, "ind": 3, "iax": 3,
    "ial": 3, "rel16": 3, "bm": 3, "abl": 4, "ablx": 4,
}

# Registradores SNES para anotacao
HW_REGS = {
    0x2100: "INIDISP", 0x2101: "OBSEL", 0x2102: "OAMADDL", 0x2103: "OAMADDH",
    0x2104: "OAMDATA", 0x2105: "BGMODE", 0x2106: "MOSAIC", 0x2107: "BG1SC",
    0x2108: "BG2SC", 0x2109: "BG3SC", 0x210A: "BG4SC", 0x210B: "BG12NBA",
    0x210C: "BG34NBA", 0x210D: "BG1HOFS", 0x210E: "BG1VOFS",
    0x210F: "BG2HOFS", 0x2110: "BG2VOFS", 0x2111: "BG3HOFS",
    0x2112: "BG3VOFS", 0x2115: "VMAIN", 0x2116: "VMADDL", 0x2117: "VMADDH",
    0x2118: "VMDATAL", 0x2119: "VMDATAH", 0x2121: "CGADD", 0x2122: "CGDATA",
    0x2123: "W12SEL", 0x212C: "TM", 0x212D: "TS", 0x2130: "CGWSEL",
    0x2131: "CGADSUB", 0x2132: "COLDATA", 0x2133: "SETINI",
    0x2140: "APUIO0", 0x2141: "APUIO1", 0x2142: "APUIO2", 0x2143: "APUIO3",
    0x2180: "WMDATA", 0x2181: "WMADDL", 0x2182: "WMADDM", 0x2183: "WMADDH",
    0x4200: "NMITIMEN", 0x4201: "WRIO", 0x4202: "WRMPYA", 0x4203: "WRMPYB",
    0x4204: "WRDIVL", 0x4205: "WRDIVH", 0x4206: "WRDIVB", 0x4207: "HTIMEL",
    0x420B: "MDMAEN", 0x420C: "HDMAEN", 0x4210: "RDNMI", 0x4212: "HVBJOY",
    0x4214: "RDDIVL", 0x4215: "RDDIVH", 0x4216: "RDMPYL", 0x4217: "RDMPYH",
    0x4218: "JOY1L", 0x4219: "JOY1H", 0x421A: "JOY2L", 0x421B: "JOY2H",
}
for ch in range(8):
    b = 0x4300 + ch * 0x10
    for off, nm in ((0, "DMAP"), (1, "BBAD"), (2, "A1TL"), (3, "A1TH"),
                    (4, "A1B"), (5, "DASL"), (6, "DASH")):
        HW_REGS[b + off] = f"{nm}{ch}"


# Known jump tables in this ROM (targets of JMP (abs,X) / JML [$00]).
# (name, snes address of the table, n entries, m, x)
# m/x = flag state on entry to the handlers (True = 8 bits).
KNOWN_JMPTABLES = [
    ("Decomp",    0x809DE5, 4, True,  True),   # decompressor modes
    ("Decomp3",   0x809DFD, 4, True,  True),   # mode-3 sub-modes
    ("PlayerSt",  0x80A811, 3, True,  True),   # player state ($0ED6)
    ("ColPlayer", 0x80ACA6, 0, True,  True),   # enemy x player collision (n via $AD62)
    ("ColShot",   0x80AE74, 0, True,  True),   # enemy x shot collision   (n via $AF6A)
    ("Story1",    0x80BD15, 3, True,  True),   # story page 1, per language
    ("Story2",    0x80BD46, 3, True,  True),
    ("Story3",    0x80BD77, 3, True,  True),
    ("GameBG",    0x80BE09, 7, True,  True),   # 7 gameplay background photos
    ("Txt1",      0x80C72E, 3, True,  True),   # per-language texts (intro pages)
    ("Txt2",      0x80C75F, 3, True,  True),
    ("Txt3",      0x80C790, 3, True,  True),
    ("Txt4",      0x80C7C1, 3, True,  True),
]
# Object handler tables: bank at $8ABA (15 bytes), addr at $8AC9
# (15 words). "init" entry = addr-3, "run" = addr. Called with REP #$30.
OBJ_BANK_TAB = 0x008ABA
OBJ_ADDR_TAB = 0x008AC9
OBJ_NTYPES = 15
# type->collision-handler-index tables
COL_PLAYER_IDX = 0x00AD62   # 48 bytes
COL_SHOT_IDX = 0x00AF6A


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("-o", "--out", default="disasm/hk97_trace.asm")
    ap.add_argument("--no-tables", action="store_true",
                    help="ignore the known jump tables")
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()

    def rd_vec(file_off: int) -> int:
        return rom[file_off] | (rom[file_off + 1] << 8)

    entries = []
    for name, off in (("RESET", 0x7FFC), ("NMI_emu", 0x7FFA),
                      ("IRQ_emu", 0x7FFE), ("NMI_nat", 0x7FEA),
                      ("IRQ_nat", 0x7FEE), ("COP_nat", 0x7FE4),
                      ("BRK_nat", 0x7FE6)):
        v = rd_vec(off)
        if 0x8000 <= v <= 0xFFFF and v != 0xFFFF:
            entries.append((name, v))

    extra: list[tuple[str, int, bool, bool]] = []  # (label, addr24, m, x)
    if not args.no_tables:
        for name, tab, n, m, x in KNOWN_JMPTABLES:
            if n == 0:
                idx_tab = COL_PLAYER_IDX if name == "ColPlayer" else COL_SHOT_IDX
                off = lorom_to_file(idx_tab | 0x800000)
                n = max(rom[off + i] for i in range(OBJ_NTYPES))
            bank = tab & 0xFF0000
            toff = lorom_to_file(tab)
            for i in range(n):
                tgt = bank | rd_vec(toff + 2 * i)
                extra.append((f"{name}_{i}", tgt, m, x))
        # object type 5 (boss): initial handler at $A355 (fields $05E0/$0940).
        # Note: for object type 6 (menu cursor) these fields point to DATA
        # ($BD01 = cursor position table), not code.
        extra.append(("Obj5Main", 0x80A355, True, True))
        # return pushed by PEA before the JML to a handler (OAM assembly)
        extra.append(("DrawObj", 0x8085CD, False, False))  # PEA $85CC -> RTL +1
        boff = lorom_to_file(OBJ_BANK_TAB | 0x800000)
        aoff = lorom_to_file(OBJ_ADDR_TAB | 0x800000)
        for i in range(OBJ_NTYPES):
            bank = rom[boff + i] << 16
            addr = rd_vec(aoff + 2 * i)
            extra.append((f"ObjRun_{i:02X}", bank | addr, False, False))
            extra.append((f"ObjInit_{i:02X}", bank | (addr - 3), False, False))

    # state: addr24 -> (m, x) on entry
    visited: dict[int, tuple] = {}   # addr24 -> (length, text)
    labels: dict[int, str] = {}
    indirect_jumps: list[int] = []
    # worklist: (addr24, m, x)  — no reset, modo emulacao: M=X=1
    work = []
    for name, v in entries:
        labels[v] = name
        work.append((v, True, True))
    for name, a24, m, x in extra:
        labels.setdefault(a24, name)
        work.append((a24, m, x))

    def label_for(a24: int, prefix: str) -> str:
        if a24 not in labels:
            labels[a24] = f"{prefix}_{a24:06X}"
        return labels[a24]

    while work:
        addr, m, x = work.pop()
        while True:
            if addr in visited:
                break
            off = lorom_to_file(addr)
            if off is None or off >= len(rom):
                break
            op = rom[off]
            mn, mode = OPCODES[op]
            if mode == "immM":
                ln = 2 if m else 3
            elif mode == "immX":
                ln = 2 if x else 3
            else:
                ln = MODE_LEN[mode]
            raw = rom[off:off + ln]
            if len(raw) < ln:
                break
            operand = int.from_bytes(raw[1:], "little")
            bank = addr >> 16
            nxt = (addr & 0xFF0000) | ((addr + ln) & 0xFFFF)

            # formatting
            note = ""
            if mode in ("abs", "absx", "absy", "ind", "iax") and mn not in (
                    "JMP", "JSR", "JML"):
                reg = HW_REGS.get(operand)
                if reg:
                    note = f" ; {reg}"
            if mode == "imp":
                txt = mn
            elif mode == "acc":
                txt = f"{mn} A"
            elif mode == "imm8":
                txt = f"{mn} #${operand:02X}"
            elif mode in ("immM", "immX"):
                txt = f"{mn} #${operand:0{(ln - 1) * 2}X}"
            elif mode == "dp":
                txt = f"{mn} ${operand:02X}"
            elif mode == "dpx":
                txt = f"{mn} ${operand:02X},X"
            elif mode == "dpy":
                txt = f"{mn} ${operand:02X},Y"
            elif mode == "idp":
                txt = f"{mn} (${operand:02X})"
            elif mode == "idpx":
                txt = f"{mn} (${operand:02X},X)"
            elif mode == "idpy":
                txt = f"{mn} (${operand:02X}),Y"
            elif mode == "idlp":
                txt = f"{mn} [${operand:02X}]"
            elif mode == "idly":
                txt = f"{mn} [${operand:02X}],Y"
            elif mode == "sr":
                txt = f"{mn} ${operand:02X},S"
            elif mode == "isry":
                txt = f"{mn} (${operand:02X},S),Y"
            elif mode == "abs":
                txt = f"{mn} ${operand:04X}{note}"
            elif mode == "absx":
                txt = f"{mn} ${operand:04X},X{note}"
            elif mode == "absy":
                txt = f"{mn} ${operand:04X},Y{note}"
            elif mode == "abl":
                txt = f"{mn} ${operand:06X}"
            elif mode == "ablx":
                txt = f"{mn} ${operand:06X},X"
            elif mode == "ind":
                txt = f"{mn} (${operand:04X})"
            elif mode == "iax":
                txt = f"{mn} (${operand:04X},X)"
            elif mode == "ial":
                txt = f"{mn} [${operand:04X}]"
            elif mode == "rel8":
                tgt = (addr & 0xFF0000) | ((addr + 2 + (
                    operand - 256 if operand >= 128 else operand)) & 0xFFFF)
                txt = f"{mn} {label_for(tgt, 'L')}"
            elif mode == "rel16":
                d = operand - 65536 if operand >= 32768 else operand
                tgt = (addr & 0xFF0000) | ((addr + 3 + d) & 0xFFFF)
                txt = f"{mn} {label_for(tgt, 'L')}"
            elif mode == "bm":
                txt = f"{mn} ${raw[2]:02X},${raw[1]:02X}"
            else:
                txt = f"{mn} ???"

            visited[addr] = (ln, txt, raw)

            # flags
            if mn == "SEP":
                m = m or bool(operand & 0x20)
                x = x or bool(operand & 0x10)
                if operand & 0x20:
                    m = True
                if operand & 0x10:
                    x = True
            elif mn == "REP":
                if operand & 0x20:
                    m = False
                if operand & 0x10:
                    x = False
            elif mn == "XCE":
                # heuristic: CLC/XCE -> native (flags kept M=X=1 until REP)
                pass

            # control flow
            if mn in ("RTS", "RTL", "RTI", "STP"):
                break
            if mn == "BRA" or mn == "BRL":
                tgt_l = txt.split()[-1]
                addr = next(a for a, l in labels.items() if l == tgt_l)
                continue
            if mn in ("BPL", "BMI", "BVC", "BVS", "BCC", "BCS", "BNE", "BEQ"):
                tgt_l = txt.split()[-1]
                t = next(a for a, l in labels.items() if l == tgt_l)
                work.append((t, m, x))
                addr = nxt
                continue
            if mn == "JMP" and mode == "abs":
                addr = (bank << 16) | operand
                label_for(addr, "L")
                continue
            if mn == "JML" and mode == "abl":
                addr = operand
                label_for(addr, "L")
                continue
            if mn == "JSR" and mode == "abs":
                t = (bank << 16) | operand
                label_for(t, "Sub")
                work.append((t, m, x))
                addr = nxt
                continue
            if mn == "JSL":
                label_for(operand, "Sub")
                work.append((operand, m, x))
                addr = nxt
                continue
            if (mn in ("JMP", "JML") and mode in ("ind", "iax", "ial")) or (
                    mn == "JSR" and mode == "iax"):
                indirect_jumps.append(addr)
                break
            if mn in ("BRK", "COP"):
                break
            addr = nxt

    # ------------------------------------------------------------- output
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append(f"; trace of {args.rom} — {len(visited)} instructions")
    lines.append(f"; vectors: " + ", ".join(f"{n}=${v:04X}" for n, v in entries))
    if indirect_jumps:
        lines.append("; INDIRECT JUMPS (not followed): " +
                     ", ".join(f"${a:06X}" for a in indirect_jumps))
    lines.append("")

    addrs = sorted(visited)
    prev_end = None
    covered = set()
    for a in addrs:
        ln, txt, raw = visited[a]
        f = lorom_to_file(a)
        for i in range(ln):
            covered.add(f + i)
        if prev_end is not None and a != prev_end:
            lines.append("")
        if a in labels:
            lines.append(f"{labels[a]}:")
        hexs = " ".join(f"{b:02X}" for b in raw)
        lines.append(f"  ${a:06X}  {hexs:<12} {txt}")
        prev_end = (a & 0xFF0000) | ((a + ln) & 0xFFFF)

    # data regions (not covered) in the file
    lines.append("")
    lines.append("; ---- UNREACHED regions (data) ----")
    i = 0
    n = len(rom)
    while i < n:
        if i in covered:
            i += 1
            continue
        j = i
        while j < n and j not in covered:
            j += 1
        # so relata blocos >= 32 bytes
        if j - i >= 32:
            bank = i // 0x8000
            a = 0x8000 + (i % 0x8000)
            lines.append(f";  file ${i:06X}..${j - 1:06X}  "
                         f"(snes ${bank:02X}:{a:04X})  {j - i} bytes")
        i = j
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ok: {out}  ({len(visited)} instructions, "
          f"{len(indirect_jumps)} indirect jumps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
