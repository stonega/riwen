-- Stock IBus: F8 applies results. Riwen frontend: main-loop properties poll safely.
-- No network wait, shell execution, timer, or automatic commit in Rime callbacks.
local M = { processor = {}, filter = {} }
local ok, socket = pcall(require, "socket")
local apply_ready, poll

local function status(state, value)
  state.context:set_property("riwen_status", value)
end

local function hex(s)
  return (s:gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

local function unhex(s)
  if #s > 144 or #s % 2 ~= 0 or s:find("[^%da-f]") then return nil end
  local value = s:gsub("..", function(pair) return string.char(tonumber(pair, 16)) end)
  return utf8.len(value) and value or nil
end

local function han(text)
  if not utf8.len(text) then return false end
  for _, code in utf8.codes(text) do
    if code < 0x3400 or code > 0x9fff then return false end
  end
  return true
end

local function correction_valid(original, text)
  if not text or #text ~= #original or text == original or not han(text) then return false end
  local changes = 0
  for i = 1, #text, 3 do
    if text:sub(i, i + 2) ~= original:sub(i, i + 2) then changes = changes + 1 end
  end
  return changes <= math.min(3, math.floor(#original / 6))
end

local function tail(s, max_bytes)
  if #s <= max_bytes then return s end
  local start = #s - max_bytes + 1
  while start <= #s and s:byte(start) >= 128 and s:byte(start) < 192 do start = start + 1 end
  return s:sub(start)
end

local function reset(state)
  state.history, state.pending, state.ready, state.applied = "", nil, nil, nil
  state.frozen = false
  state.context:set_property("riwen_choice", "")
  status(state, "idle")
end

local function get_state(env)
  local context = env.engine.context
  -- engine.context wrappers may differ between Lua calls; use a context property
  -- to associate processor and filter with the same session table.
  local token = context:get_property("riwen_session")
  local state = token ~= "" and M.live[token] or nil
  if state then return state end
  M.serial = M.serial + 1
  token = tostring(M.serial)
  local mode = context:get_property("riwen_mode")
  state = { history = "", counter = 0, last = 0, refs = 0, context = context,
            mode = (mode == "auto" or mode == "off") and mode or "manual" }
  if ok then
    local udp = socket.udp()
    if udp then
      udp:settimeout(0)
      local bound = udp:setsockname("127.0.0.1", 0)
      local port = env.engine.schema.config:get_int("riwen/port") or 18765
      if bound and udp:setpeername("127.0.0.1", port) then state.udp = udp
      else udp:close() end
    end
  end
  state.connection = context.commit_notifier:connect(function(ctx)
    if state.mode == "off" then return end
    local now = ok and socket.gettime() or 0
    if now - state.last > 30 then reset(state) end
    state.history = tail(state.history .. ctx:get_commit_text(), 768)
    state.pending, state.ready, state.applied = nil, nil, nil
    state.frozen = false
    ctx:set_property("riwen_choice", "")
    status(state, "idle")
    state.last = now
  end)
  if context.property_update_notifier then
    state.property_connection = context.property_update_notifier:connect(function(ctx, name)
      if name == "riwen_mode" then
        local mode = ctx:get_property(name)
        state.mode = (mode == "auto" or mode == "off") and mode or "manual"
        reset(state)
      elseif name == "riwen_reset" then
        reset(state)
      elseif name == "riwen_poll" and state.mode == "auto" and not state.frozen then
        -- Called synchronously from the frontend's GLib main loop, never a worker.
        apply_ready(state, ctx)
      end
    end)
  end
  M.live[token] = state
  context:set_property("riwen_session", token)
  state.token = token
  return state
end

M.live, M.serial = {}, 0

local function init(env)
  env.riwen = get_state(env)
  env.riwen.refs = env.riwen.refs + 1
end

local function fini(env)
  local state = env.riwen
  if not state then return end
  state.refs = state.refs - 1
  if state.refs == 0 then
    state.connection:disconnect()
    if state.property_connection then state.property_connection:disconnect() end
    if state.udp then state.udp:close() end
    M.live[state.token] = nil
  end
  env.riwen = nil
end

apply_ready = function(state, context)
  poll(state)
  if state.ready and state.pending and state.ready.input == context.input and
     socket.gettime() - state.pending.at < state.pending.ttl and not state.applied then
    state.applied = state.ready
    context:refresh_non_confirmed_composition()
    return true
  end
  return false
end

poll = function(state)
  if not state.udp then return end
  for _ = 1, 16 do
    local packet = state.udp:receive(512)
    if not packet then break end
    local id, best, outcome = packet:match("^R1\t(%d+)\t(%d+)\t(%a+)$")
    local pending = state.pending
    local correction_id, encoded, correction_outcome = packet:match("^R2\t(%d+)\t([%da-f]*)\t(%a+)$")
    if pending and pending.kind == "R2" and correction_id == pending.id and
       socket.gettime() - pending.at < pending.ttl then
      local text = unhex(encoded)
      if correction_outcome == "ok" and correction_valid(pending.original, text) then
        state.ready = { key = pending.key, input = pending.input, correction = text }
      else
        status(state, "fallback")
      end
    end
    best = tonumber(best)
    if pending and pending.kind == "R1" and id == pending.id and outcome == "fallback" then
      state.ready = nil
      status(state, "fallback")
    elseif pending and pending.kind == "R1" and id == pending.id and outcome == "ok" and best and
       best >= 1 and best <= pending.count and socket.gettime() - pending.at < pending.ttl then
      state.ready = { key = pending.key, input = pending.input, best = best }
    end
  end
end

function M.processor.func(key, env)
  local state, context = env.riwen, env.engine.context
  if not state then return 2 end
  local now = ok and socket.gettime() or 0
  if now - state.last > 30 then reset(state) end
  state.last = now
  if key:release() then return 2 end
  -- F9 clears tracked context after moving between documents/applications.
  if key:repr() == "F9" then
    reset(state)
    context:refresh_non_confirmed_composition()
    return 1
  end
  -- Edits/navigation invalidate commit history; exact surrounding text is unknown.
  local repr = key:repr()
  if context:has_menu() and (repr == "Up" or repr == "Down" or repr == "Tab" or
     repr == "Shift+Tab" or repr == "Prior" or repr == "Next" or repr == "minus" or repr == "equal") then
    state.frozen = true
    status(state, "frozen")
  end
  if repr:find("BackSpace", 1, true) or repr:find("Delete", 1, true) or
     repr:find("Left", 1, true) or repr:find("Right", 1, true) or
     repr:find("Home", 1, true) or repr:find("End", 1, true) or
     repr:find("Control", 1, true) or repr:find("Super", 1, true) then
    reset(state)
    return 2
  end
  if not context:has_menu() and (repr == "Up" or repr == "Down" or
     repr == "Prior" or repr == "Next") then
    reset(state)
    return 2
  end
  if repr ~= "F8" or not context:has_menu() then return 2 end
  if not apply_ready(state, context) then
    -- A second F8 after the result arrives applies it; never wait here.
    if state.pending and socket.gettime() - state.pending.at >= state.pending.ttl then
      state.pending = nil
    end
    context:refresh_non_confirmed_composition()
  end
  return 1
end

local function eligible(candidate)
  return (candidate.type == "phrase" or candidate.type == "user_phrase" or
          candidate.type == "sentence") and candidate.quality < 90 and
         #candidate.text <= 192
end

function M.filter.func(translation, env)
  local state, context = env.riwen, env.engine.context
  -- Display metadata only: never add a badge to a candidate's committed text.
  context:set_property("riwen_choice", "")
  local candidates = {}
  -- Rime returns a generic-for iterator triple, not a zero-argument closure.
  local next_candidate, iterator_state, iterator_key = translation:iter()
  local function rest()
    iterator_key = next_candidate(iterator_state, iterator_key)
    return iterator_key
  end
  for _ = 1, 8 do
    local candidate = rest()
    if not candidate then break end
    candidates[#candidates + 1] = candidate
  end
  local input = context.input
  local first = candidates[1]
  local base_valid = state and state.mode ~= "off" and state.udp and #input >= 4 and
    #input <= 64 and not input:find("[^a-z']") and context.caret_pos == #input and
    first and eligible(first)
  local generate = base_valid and first.start == 0 and first._end == #input and
    #first.text >= 18 and #first.text <= 72 and han(first.text)
  local valid = base_valid and #state.history > 0 and #candidates >= 2
  if valid and not generate then
    for _, candidate in ipairs(candidates) do
      if not eligible(candidate) or candidate.start ~= first.start or
         candidate._end ~= first._end then valid = false; break end
    end
  end
  if valid or generate then
    local fields = { hex(state.history), hex(input) }
    local kind = generate and "R2" or "R1"
    if generate then
      local pinyin = (first.preedit or ""):gsub("[^a-z' ]", ""):gsub(" +", " "):match("^%s*(.-)%s*$")
      fields[#fields + 1] = hex(pinyin)
      fields[#fields + 1] = hex(first.text)
    else
      for _, candidate in ipairs(candidates) do fields[#fields + 1] = hex(candidate.text) end
    end
    local key = kind .. "\t" .. table.concat(fields, "\t")
    if state.applied and state.applied.key == key then
      local best
      if state.applied.correction then
        for index, candidate in ipairs(candidates) do
          if candidate.text == state.applied.correction and candidate.start == first.start and candidate._end == first._end then
            best = table.remove(candidates, index); break
          end
        end
        if not best then
          best = Candidate("riwen", first.start, first._end, state.applied.correction, "")
          best.quality = first.quality
          best.preedit = first.preedit
        end
      else
        best = table.remove(candidates, state.applied.best)
      end
      table.insert(candidates, 1, best)
      context:set_property("riwen_choice", best.text)
      status(state, "applied")
    elseif not state.pending or state.pending.key ~= key then
      state.counter = state.counter + 1
      local id = tostring(state.counter)
      state.pending = { id = id, key = key, input = input, count = #candidates, at = socket.gettime(),
                        ttl = generate and 4 or 2, kind = kind, original = first.text }
      state.ready, state.applied = nil, nil
      state.frozen = false
      state.udp:send(kind .. "\t" .. id .. "\t" .. table.concat(fields, "\t"))
      status(state, generate and "pending-correction" or "pending")
    end
  else
    if state then
      state.pending, state.ready, state.applied = nil, nil, nil
      status(state, state.udp and "idle" or "socket-unavailable")
    end
  end
  for _, candidate in ipairs(candidates) do yield(candidate) end
  for candidate in rest do yield(candidate) end
end

M.processor.init, M.filter.init = init, init
M.processor.fini, M.filter.fini = fini, fini
return M
