-- Exercise live gameplay until an original explosion object is visible.
-- OBJ_BASE is the linked address of hk_objects from the SDCC map.

local SHOT = assert(os.getenv("SHOT"), "SHOT env var required")
local BASE = tonumber(assert(os.getenv("OBJ_BASE"), "OBJ_BASE env var required"))
local OUT = os.getenv("PROBE_LOG")
local MAX_FRAMES = tonumber(os.getenv("FRAMES") or "2400")
local MEM = emu.memType.smsDebug
local STRIDE = 17
local frame = 0
local explosion_frame = nil
local seen = {}
local last_input_frame = -1
local cached_input = nil

local function input_for_frame(n)
  local one = false
  local right = false
  if n >= 40 and n < 700 then
    one = (n % 55) < 4
  elseif n >= 700 then
    -- Sweep the full playfield while firing to exercise a natural collision.
    local left = (math.floor((n - 700) / 110) % 2) == 0
    right = not left
    one = (n % 12) < 4
    return { one = one, two = false, left = left, right = right,
             up = false, down = false }
  end
  return { one = one, two = false, left = false,
           right = right, up = false, down = false }
end

local function on_input_polled()
  if frame ~= last_input_frame then
    cached_input = input_for_frame(frame)
    last_input_frame = frame
  end
  emu.setInput(cached_input, 0)
end

local function on_end_frame()
  frame = frame + 1
  if not explosion_frame and frame % 15 == 0 then
    -- A shot is removed immediately before the explosion is spawned, so the
    -- first-free allocator places normal explosions in slot zero.
    for i = 0, 0 do
      local kind = emu.read(BASE + i * STRIDE, MEM)
      seen[kind] = (seen[kind] or 0) + 1
      if kind == 11 or kind == 13 or kind == 14 then
        -- Rendering runs every third VBlank; allow one full render interval.
        explosion_frame = frame + 3
        break
      end
    end
  elseif frame == explosion_frame then
    local png = emu.takeScreenshot()
    local f = assert(io.open(SHOT, "wb"))
    f:write(png)
    f:close()
  elseif explosion_frame and frame >= explosion_frame + 15 then
    emu.stop(0)
  end
  if frame >= MAX_FRAMES and not explosion_frame then
    if OUT then
      local f = assert(io.open(OUT, "w"))
      f:write("No explosion object observed through frame ", frame, "\n")
      for kind, count in pairs(seen) do
        f:write(string.format("type %02d: %d samples\n", kind, count))
      end
      f:close()
    end
    emu.stop(2)
  end
end

emu.addEventCallback(on_input_polled, emu.eventType.inputPolled)
emu.addEventCallback(on_end_frame, emu.eventType.endFrame)
