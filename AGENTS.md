<!-- BEGIN conversion-desk:thread-rules:v2 -->
# Conversion Desk — Thread Rules

Planted and refreshed by the desk (`scripts/plant_project_rules.py`). Edit the
source at `knowledge/THREAD-RULES.md` in the desk, not this copy. Anything below
the END marker belongs to this repository and is never touched.

These rules cover research discipline, how a request survives a session, and the one
architectural constraint that no project may renegotiate (Rule 12). Fidelity targets and
build contracts belong to this repository and to the desk's own instructions.

The desk holds the reusable knowledge: platform internals, measured constants,
tool notes, archived manuals, and what every other conversion already learned.
Reach it one of two ways:

- **On the machine that holds the desk checkout:** grep it directly. The whole
  corpus is a few megabytes and answers in milliseconds.
- **Anywhere else:** the knowledge API. Never assume the files are reachable —
  most machines do not have them. It needs no token; the base URL is in the desk's
  `knowledge/KNOWLEDGE-API.md`.

Submitting is not optional bookkeeping. A conversion that measures something and
does not submit it leaves the next conversion to measure it again.

## Rule 1 — A negative claim is a hypothesis, never a conclusion

**Trigger:** you are about to write that something is impossible, blocked,
locked, encrypted, unsupported, or a limitation of the platform, tool, or
emulator.

Before that sentence is allowed to exist:

1. Check the desk — grep it, or ask the API.
2. Run at least one online search naming **the specific mechanism you claim is
   blocking**, not the general topic.
3. Submit the claim to the knowledge API before acting on it.

If all three do not fit, the honest sentence is *"I have not investigated X
yet."* That does not close a path and does not become a fact.

Measured: a thread closed an entire target platform on five seconds of search,
lost two hours to the detour, and the blocker did not exist.

## Rule 2 — Two failed attempts end the guessing

**Trigger:** you are starting a second attempt at the same thing without new
information having arrived between attempts.

A third attempt is not allowed. Instead: return to the source of truth
(disassembly, ROM or disc bytes, original source, symbol map, official
documentation), search online, or ask the API and keep working on whatever does
not depend on the answer.

A new idea about what might be wrong is not new information. A measurement, a
document, a trace, or a tool output is.

## Rule 3 — The desk is checked before the web

**Trigger:** you are about to search the web about a platform, tool, file
format, or one of our projects.

Check the desk first. If it genuinely has nothing, search online — then archive
what you found back into the desk so the next thread does not repeat it.

Published knowledge is written in English while threads often work in
Portuguese. A literal keyword search across that boundary silently returns
nothing; search both languages, or ask the API.

## O QUE FOI PEDIDO

<!-- Preencher com o pedido literal, nas palavras em que foi dado, com data.
     Não parafrasear. Não substituir por roadmap. A sessão abre lendo isto e
     fecha dizendo o que fez contra isto. -->

- 2026-08-31 — "Vamos converter o hong kong 97 para master system. Já convertemos pra mega drive, entao todo o trabalho de disassembly e compreensão já está feito. a conversão deve ser mais simples, precisando de pouco demake."
- 2026-09-02 — "vamos converter o jogo ../hong-kong-97-sms para o gamegear"
- 2026-09-02 — "os textos da tela titulo e da intro estao ilegiveis"
- 2026-09-02 — "ok, essa será a versão 0.0.1"
- 2026-09-02 — "ok, reune o repo, renomeia pra hong-kong-97-sega-8bit"
- 2026-09-02 — "arruma no meu readme"

## Rule 4 — The request, written down, outlives the session

**Trigger:** you are starting a session, and you are ending one.

Measured across four projects: the delivered work was not the requested work in
four cases out of four. Every step was locally defensible; none was the request.

- The request lives at the top of this file, verbatim and dated.
- A session opens by reading it and closes by stating what it did against it.
- Work outside that list is not forbidden — it is evidence of drift. Stop and
  ask. A cheap question beats eight hours in the wrong direction.
- An architecture implied by the request ("keep the original running", "move
  rendering off the 68000") is part of the request. Replacing it is a decision,
  and an undecidable one is a negative claim under Rule 1.

## Rule 5 — An instrument whose failures are not true is worse than none

**Trigger:** you are about to trust a number that says the work is correct.

A progress metric reached 100% with no playable build, because it counted
analysis coverage; it never failed, so it was believed. A parity sweep reported
180 false divergences from a window boundary; it failed almost everything, so it
stopped being read.

- A metric that can reach 100% without the deliverable existing is wrong by
  construction.
- Before raising an alarm from a number, read the comparator, not its output.
- An instrument is regenerated by the command that builds. A report refreshed by
  hand is one that eventually is not.
- Remove the cause of a false failure rather than widening tolerance for it.

## Rule 6 — The source of truth is an oracle, never a backlog

**Trigger:** you need a value you do not have, or you are choosing what to port
next.

- Never guess a jump height, position, timing, or constant that the disassembly
  answers. There is no acceptable guess for a value that exists.
- Never walk the disassembly front to back as a task queue. `batch 26` is not
  consulting the source; it is using its label list as a roadmap, and that list
  has no end and no relation to the deliverable.

Consultation is mandatory; traversal is prohibited. What to port next comes from
what the requested slice needs.

## Rule 7 — Your memory of a tool is a lower bound, and it is always stale

**Trigger:** you are about to state what an emulator, library, SDK, or toolchain
does or does not support, from what you already know rather than from what is
installed.

Training data is always older than the tool on this machine. So recall about
actively-developed software is a **lower bound on its capabilities**, and the
error is one-directional: it never invents a feature that does not exist, it
denies one that was added after the cutoff. That is why this failure always
appears as a wall, never as a phantom capability — and why a negative memory is
the single least trustworthy thing you can act on.

Measured: the desk published "DREQ streaming is not emulated in the ares CD
combo". A thread read it and was about to design around a 131,040-byte ceiling.
The ares source on this machine implements DREQ end to end — FIFO port, control
register, SH-2 DMAC consumer, and a game-specific compatibility case. The
statement was true for some older ares and was published without a version.

- Before a capability claim closes a path, check the installed thing: read the
  source when it is open, or the release notes for the version actually present.
  Not the version you remember.
- Record the version or commit with the claim. `ares-for-ai f6ea42064` is a fact;
  "ares does not support X" rots the moment upstream merges a pull request.
- The symptom you observed stays measured; the cause you recalled does not get
  published as fact. A hang, a black screen, and ~1 VPS are observations. "Not
  emulated" is an explanation, and it needs the same evidence as any other.
- This is not licence to re-verify everything. It fires on capability claims
  about third-party software under active development, and hardest on the
  negative ones.

## Rule 8 — Never state a duration

**Trigger:** you are about to write that something takes minutes, hours, days,
or weeks — in a plan, an estimate, a justification, or an offer to cut scope.

Do not. Not "roughly", not "probably", not "a multi-hour build". You have no
clock and no memory of your own throughput. Your sense of duration comes from a
training corpus written by and about human teams, so it is calibrated to a
different actor entirely — and the error is always inflation, never the reverse.

Measured here: a thread called an FMV player build a "multi-hour assembly
build" and offered to shorten the test video because of it. Challenged, it timed
the real thing: **13 seconds** for the whole CD32X build — both 68000 parts, the
SH-2 part, the link, `mkisofs -G` with the boot block, and ISO verification.
Three orders of magnitude, invented, and it had already been used to propose
cutting the deliverable in half. Its own diagnosis was correct: it had confused
its history of being slow with the cost of the work.

An inflated cost never widens the work, it only shrinks it. That makes a
fabricated duration the most common justification for abandoning the request
under Rule 4.

**What to say instead:**

- Count the work, do not time it. "Fourteen opcodes the room executes", "six
  discs", "three rooms diverge" — countable, checkable, and it does not rot.
- If duration genuinely decides something, **measure one unit and say so**:
  build once, time it, multiply. Timing one iteration is almost always cheaper
  than arguing about the estimate.
- When you have been slow, the null hypothesis is that your process was slow,
  not that the task is expensive. Check that before proposing a smaller task.

## Rule 9 — Delegation is not progress, and a running agent is not an artifact

**Trigger:** you are about to hand the task you were asked to do to a subagent,
or you are about to report activity instead of a result.

Measured here: told to stop delegating and do the work, an agent committed the
verification gate, then spawned a subagent for the actual build at 01:17 and let
it run until 02:08 — **fifty-one minutes** — with nothing landing. Ten seconds
after the subagent was stopped, it began doing the work itself. In the same
session it had already diagnosed this exact defect in its own history:
"delegating blind, delivering unverified, and you had to test it for me." It
named the mechanism correctly and repeated it within the hour. Self-knowledge
binds nothing.

- Do not delegate the task you were asked to do. Splitting off genuinely
  parallel, independently checkable work is fine; handing off the core of the
  request is not.
- Whatever you delegate, you own verifying before it counts. An unverified
  subagent result is not a result, it is a claim.
- A work log entry, a spawned agent, and a running command are not artifacts.
  Elapsed activity is not progress.
- If nothing the user can inspect has landed, that is the report. Say it plainly
  and early — much earlier than an hour.

## Rule 10 — Never add CI to a conversion repository unless it was asked for

**Trigger:** you are about to create `.github/workflows/`, a workflow file, or
any other hosted-CI configuration.

Do not. These repositories are private, so every workflow run bills against a
finite pool of minutes that belongs to one person, and a conversion repository
rebuilds ROMs, discs and emulator captures — the most expensive thing that pool
could possibly be spent on. Three repositories had picked up workflows nobody
requested, two of them invoking an agent on every push and pull request.

- Verification runs locally, through the repository's own `make` targets. That
  is where the gates already live, and it costs nothing.
- If CI is genuinely wanted, the person paying for the minutes asks for it. It
  is never a default, never scaffolding, and never a side effect of
  initialising a repository.
- The same applies to anything that schedules itself: cron workflows, watchers,
  bots, and auto-merge.

## Rule 11 — Nothing durable lives in `/tmp`

**Trigger:** you are about to write a path beginning with `/tmp/` into a script,
a Makefile, or a command that produces an artifact you will read again.

Several conversions run on this machine at the same time and they share one
`/tmp`. Measured while writing this rule: 5.9 GB of 7.3 GB used, of which 3.2 GB
was project working directories — a 1.6 GB CI tree, a 707 MB window capture, two
trace directories from a third project. When it fills, commands that produce
output start failing **without an error message**, and the session that suffers
is rarely the one that filled it.

- Working files, captures, traces, dumps and intermediate builds go inside the
  repository, in a directory listed in its `.gitignore` — `build/`, `out/`,
  `exports/`, whatever that project already uses.
- A genuinely ephemeral scratch file is fine through `mktemp`, provided the same
  command removes it. A hard-coded `/tmp/...` path in a tracked script is not
  ephemeral; it is an artifact with no owner.
- The desk keeps `tmp/` at its root for this, already gitignored.
- If something must be large, put it where the disk is large and say so — never
  by discovering the ceiling at the moment another thread hits it.

## Rule 12 — A conversion converts; it never emulates

**Trigger:** you are deciding how the original game's behaviour will run on the
target — any source, any target, PC or console — or you are about to write,
vendor, or generate anything that steps the original program.

The port's logic is source written for the target: readable, editable, and
portable to the next target. Nothing that was asked for survives if the artifact
executes the original code instead. An emulator for the source machine already
exists and is better than the one we would write, so shipping one delivers
nothing, and it delivers nothing while looking like a finished game. That is why
this defect keeps passing review.

**Forbidden as the thing that ships, with no exception:**

- A CPU interpreter executing the original program.
- The original ROM embedded as a blob for the port to run.
- **Machine-generated translation of the original code**, whether or not any file
  is called `cpu`. Generated source marked *do not hand-edit* that carries a
  program counter is the same defect with the fetch loop unrolled — it is a
  translation layer, not a port, and it fails every reason the port was asked
  for: it cannot be read, cannot be changed, and cannot be carried to the next
  console.
- Emulating the source machine's sound CPU so it can run the original audio
  driver.

**Allowed, and how the good ports are built:**

- A CPU interpreter as the differential-test oracle — the harness that proves,
  routine by routine, that the converted logic matches the original. This is the
  correct use, and it is where the interpreter earns its keep.
- Reproducing a sound *chip*: synthesising what a YM2151, PSG or DSP produces is
  the port work, because the target has no such chip. Running the original
  driver *program* on an emulated sound CPU is not the same thing and is not
  allowed.
- Reading the disassembly and writing the behaviour for the target. That is the
  job. When the disassembly does not answer something, improve the disassembly.

**Measured here, five outcomes:**

- Alex Kidd (SMS→PC) decided it up front — no emulation at runtime, the Z80
  interpreter is dev-only — and the game binary's dependency graph contains no
  CPU at all. **This is the shape to copy.**
- Moon Patrol (arcade→PC) built ROM, CPU and video around an emulated core in
  its first commit, then corrected itself the same day: one commit established
  the native boundary, the next moved the executable onto it. Its emulated core
  survives behind a feature that is off by default.
- The first Virtua Racing PC port linked its SH-2 core into the shipping binary
  and was still doing so at commit 647. It was replaced by a repository that
  started over.
- Killer Instinct (SNES→PC) converts its game logic and then emulates the SPC700
  to play the original audio driver. Half a port.
- Keystone Kapers (2600→Genesis) shipped the original 4 KiB ROM as a C array
  inside the Mega Drive cartridge, executed by a 6502 interpreter with a
  generated 50%-coverage translation layer for speed. **It works — 60 fps,
  fidelity measured, audio exact — and it is still not a conversion.** That it
  passed as a success, and was then cited to a new project as "our methodology",
  is exactly why this rule refuses the exception. A translation layer that works
  is more dangerous than one that does not, because it propagates.

**And on this desk the PC port is upstream of the console port.** Since
2026-08-13 the console conversions that were going badly were paused and
restarted as PC ports first — Final Fight 2, Killer Instinct, Zelda, Sonic
Pocket Adventure, Chrono Trigger, Castlevania, Space Cadet Pinball, Alex Kidd,
Virtua Racing. That makes this rule load-bearing for everything downstream: a PC
port whose logic is an interpreter cannot seed the Mega Drive port, because
there is nothing to carry over. A PC port written as readable source can, and
that is the whole reason the pivot was made.

**Therefore, when you are told to convert a game:** the deliverable is the game's
logic, expressed in source for the target. If you cannot see how to write a
routine for the target, that is a disassembly problem or a hardware-knowledge
problem, and both are solved by working on them — never by handing the original
code to an interpreter and moving on.

<!-- END conversion-desk:thread-rules:v2 -->
