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

test("no inference without context", function()
  run(candidates()); assert(#sent == 0)
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
  run(candidates()); respond(2); now = now + 3
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
test("auxiliary codes and mid-composition cursor positions bypass ranking", function()
  fresh(); context.input = "igui`a"; context.caret_pos = 6
  run(candidates()); assert(#sent == 0)
  context.input = "igui"; context.caret_pos = 2
  run(candidates()); assert(#sent == 0)
end)
test("editing, reset, and inactivity clear context", function()
  for _, repr in ipairs({ "BackSpace", "Left", "Control+v", "F9" }) do
    fresh(); riwen.processor.func(key(repr), processor); assert(state.history == "")
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
test("shutdown disconnects callbacks and releases socket exactly when both components finish", function()
  riwen.processor.fini(processor); assert(not closed)
  riwen.filter.fini(filter); assert(closed and disconnected)
end)
print(count .. " tests passed")
