package.path = "./rime/lua/?.lua;" .. package.path
local now, sent, incoming, closed = 100, {}, {}, false
local udp = {
  settimeout = function(_, t) assert(t == 0) end,
  setsockname = function() return true end,
  setpeername = function() return true end,
  send = function(_, packet) sent[#sent + 1] = packet; return true end,
  receive = function() return table.remove(incoming, 1) end,
  close = function() closed = true end,
}
package.loaded.socket = { udp = function() return udp end, gettime = function() return now end }
local riwen = require("riwen")
local properties, committed, callback, disconnected = {}, "", nil, false
local context = {
  input = "igui", caret_pos = 4,
  get_property = function(_, key) return properties[key] or "" end,
  set_property = function(_, key, value) properties[key] = value end,
  get_commit_text = function() return committed end,
  has_menu = function() return true end,
  refresh_non_confirmed_composition = function() end,
  commit_notifier = { connect = function(_, fn)
    callback = fn
    return { disconnect = function() disconnected = true end }
  end },
}
local function key(repr, release)
  return { repr = function() return repr end, release = function() return release or false end }
end
local processor = { engine = { context = context, schema = { config = { get_int = function() return nil end } } } }
local filter = { engine = processor.engine }
riwen.processor.init(processor); riwen.filter.init(filter)
assert(processor.riwen == filter.riwen, "components must share the same session")
local state = processor.riwen
local function candidates()
  local out = {}
  for _, text in ipairs({ "城市", "程式", "诚实", "乘势", "成事", "成诗", "称是", "城石", "tail1", "tail2" }) do
    out[#out + 1] = { text = text, type = "phrase", quality = 1, start = 0, _end = 4 }
  end
  return out
end
local function run(values)
  local output = {}
  _G.yield = function(candidate) output[#output + 1] = candidate end
  local translation = { iter = function()
    local index = 0
    local token = {}
    return function(state)
      assert(state == token, "iterator state must be retained")
      index = index + 1
      return values[index]
    end, token, nil
  end }
  riwen.filter.func(translation, filter)
  return output
end
local function commit(text) committed = text; callback(context) end
local function respond(best, id) incoming[#incoming + 1] = "R1\t" .. (id or state.pending.id) .. "\t" .. best .. "\tok" end
local function fresh()
  riwen.processor.func(key("F9"), processor)
  context.input, context.caret_pos = "igui", 4
  sent, incoming = {}, {}
  commit("我用Python写了一个")
end
local count = 0
local function test(name, fn) fn(); count = count + 1; print("ok " .. count .. " - " .. name) end

test("first phrase requests ranking without previous commits", function()
  riwen.processor.func(key("i"), processor)
  run(candidates()); assert(#sent == 1 and state.history == "")
  respond(2); riwen.processor.func(key("F8"), processor)
  assert(run(candidates())[1].text == "程式")
end)
test("request is asynchronous and Space never silently applies a late result", function()
  fresh()
  local result = run(candidates()); assert(result[1].text == "城市" and #sent == 1)
  respond(2)
  assert(riwen.processor.func(key("space"), processor) == 2)
  assert(not state.applied)
  assert(run(candidates())[1].text == "城市")
  for _, repr in ipairs({ "1", "2", "Return", "Down", "Next" }) do
    assert(riwen.processor.func(key(repr), processor) == 2)
    assert(not state.applied)
  end
end)
test("F8 applies ready choice and preserves all candidate objects", function()
  local original = candidates()
  assert(riwen.processor.func(key("F8"), processor) == 1)
  local result = run(original)
  assert(result[1] == original[2] and result[2] == original[1])
  assert(#result == #original and result[9] == original[9])
end)
test("stale request IDs and stale input cannot change candidates", function()
  fresh(); run(candidates()); local old_id = state.pending.id
  context.input = "gsui"
  run(candidates()); respond(2, old_id)
  riwen.processor.func(key("F8"), processor)
  assert(not state.applied)
end)
test("different candidate lists invalidate previous results", function()
  fresh(); run(candidates()); respond(2)
  riwen.processor.func(key("F8"), processor)
  local values = candidates(); values[2].text = "changed"
  assert(run(values)[1].text == "城市")
end)
test("expired responses and invalid indices are ignored", function()
  fresh(); run(candidates()); respond(9)
  riwen.processor.func(key("F8"), processor); assert(not state.applied)
  run(candidates()); respond(2); now = now + 5
  riwen.processor.func(key("F8"), processor); assert(not state.applied)
end)
test("custom phrases, high priority candidates, and mixed segments are untouched", function()
  for _, change in ipairs({ { type = "user_table" }, { quality = 99 }, { _end = 2 } }) do
    fresh(); local values = candidates()
    for k, v in pairs(change) do values[2][k] = v end
    local result = run(values)
    assert(#sent == 0 and result[1] == values[1])
  end
end)
test("ordinary candidate prefix ranks while later custom candidates keep their positions", function()
  fresh(); local values = candidates(); values[4].type = "user_table"
  local result = run(values)
  assert(#sent == 1 and state.pending.count == 3 and result[4] == values[4])
  respond(2); riwen.processor.func(key("F8"), processor)
  result = run(values)
  assert(result[1] == values[2] and result[4] == values[4])
  values[4].text = "new custom phrase"
  assert(run(values)[1] == values[1] and #sent == 2)
end)
test("auxiliary codes and mid-composition cursor positions bypass ranking", function()
  fresh(); context.input = "igui`a"; context.caret_pos = 6
  run(candidates()); assert(#sent == 0)
  context.input = "igui"; context.caret_pos = 2
  run(candidates()); assert(#sent == 0)
end)
test("composition edits preserve preceding commits and invalidate old choices", function()
  for _, repr in ipairs({ "BackSpace", "Delete", "Left", "Right", "Home", "End" }) do
    fresh(); run(candidates()); respond(2)
    local history, id = state.history, state.pending.id
    context.caret_pos = 2
    riwen.processor.func(key(repr), processor)
    assert(state.history == history, repr .. " discarded preceding commits")
    assert(not state.pending and not state.ready and not state.applied)
    context.caret_pos = #context.input
    run(candidates())
    assert(state.pending.id ~= id)
    incoming = {}; respond(2, id)
    riwen.processor.func(key("F8"), processor)
    assert(not state.applied, "an edit reused a stale choice")
  end
end)
test("editing at a composition boundary conservatively clears context", function()
  for _, edit in ipairs({ { "BackSpace", 0 }, { "Left", 0 }, { "Delete", 4 }, { "Right", 4 } }) do
    fresh(); context.caret_pos = edit[2]
    riwen.processor.func(key(edit[1]), processor)
    assert(state.history == "")
  end
end)
test("two-key script inputs can rank but single initials do not", function()
  fresh(); context.input, context.caret_pos = "hf", 2
  local values = candidates()
  for _, candidate in ipairs(values) do candidate._end = 2 end
  run(values)
  assert(#sent == 1 and state.pending.count == 8)
  respond(2); riwen.processor.func(key("F8"), processor)
  assert(run(values)[1] == values[2])
  fresh(); context.input, context.caret_pos = "h", 1
  run(values); assert(#sent == 0)
end)
test("slower rankings remain valid within the extended expiry only", function()
  for _, age in ipairs({ 2.5, 4.1 }) do
    fresh(); run(candidates()); respond(2); now = now + age
    riwen.processor.func(key("F8"), processor)
    if age < 4 then assert(state.applied and state.applied.best == 2)
    else assert(not state.applied) end
  end
end)
test("document editing, reset, and inactivity clear context", function()
  for _, repr in ipairs({ "BackSpace", "Left", "Control+v", "F9" }) do
    fresh(); context.input, context.caret_pos = "", 0
    riwen.processor.func(key(repr), processor); assert(state.history == "")
  end
  fresh(); now = now + 31
  riwen.processor.func(key("a"), processor); assert(state.history == "")
end)
test("context is bounded without breaking UTF-8", function()
  fresh(); commit(string.rep("字", 400)); assert(#state.history <= 768)
  assert(utf8.len(state.history) == 256)
end)
test("document navigation clears context when no candidate menu is active", function()
  fresh()
  context.has_menu = function() return false end
  riwen.processor.func(key("Down"), processor)
  assert(state.history == "")
  context.has_menu = function() return true end
end)
test("missing service retains native candidates", function()
  fresh(); local values = candidates(); run(values)
  riwen.processor.func(key("F8"), processor)
  assert(run(values)[1] == values[1])
end)
test("a fallback stops pending status without adding a Qwen badge", function()
  fresh(); local values = candidates(); run(values)
  incoming[#incoming + 1] = "R1\t" .. state.pending.id .. "\t1\tfallback"
  riwen.processor.func(key("F8"), processor)
  assert(properties.riwen_status == "fallback")
  assert(properties.riwen_choice == "" and not state.applied)
  assert(run(values)[1] == values[1])
end)
test("scheme alphabet and short table codes work without enabling phonetic correction", function()
  fresh()
  local old_alphabet, old_minimum, old_correction = state.alphabet, state.min_input, state.correction
  state.alphabet, state.min_input, state.correction = "ab;123", 1, false
  context.input, context.caret_pos = "a;3", 3
  local values = candidates()
  for _, candidate in ipairs(values) do candidate.type, candidate._end = "table", 3 end
  run(values)
  assert(#sent == 1 and state.pending.kind == "R1")
  respond(2); riwen.processor.func(key("F8"), processor)
  assert(run(values)[1].text == "程式")
  state.alphabet, state.min_input, state.correction = old_alphabet, old_minimum, old_correction
end)
test("slower corrections can arrive after four seconds but expired replies are rejected", function()
  for _, age in ipairs({ 4.5, 6.1 }) do
    fresh()
    context.input = "nihcveuizfmohvui"
    context.caret_pos = #context.input
    local original = { text = "你好这是怎抹灰是", type = "sentence", quality = 1,
      start = 0, _end = #context.input, preedit = "ni hao zhe shi zen mo hui shi" }
    run({ original })
    assert(state.pending.kind == "R2")
    local encoded = ("你好这是怎么回事"):gsub(".", function(c) return string.format("%02x", c:byte()) end)
    incoming[#incoming + 1] = "R2\t" .. state.pending.id .. "\t" .. encoded .. "\tok"
    now = now + age
    riwen.processor.func(key("F8"), processor)
    if age < 5 then assert(state.applied and state.applied.correction == "你好这是怎么回事")
    else assert(not state.applied) end
  end
end)
test("shutdown disconnects callbacks and releases socket exactly when both components finish", function()
  riwen.processor.fini(processor); assert(not closed)
  riwen.filter.fini(filter); assert(closed and disconnected)
end)
print(count .. " tests passed")
