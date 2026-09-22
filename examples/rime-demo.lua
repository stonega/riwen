-- Headless API fixture + real Riwen extension/socket/service/model.
-- This does not create an IBus session or touch the active input method.
package.path = "./rime/lua/?.lua;" .. package.path
local socket = require("socket")
local riwen = require("riwen")
local properties, on_commit, output = {}, nil, {}
local context = {
  input = "igui", caret_pos = 4,
  get_property = function(_, name) return properties[name] or "" end,
  set_property = function(_, name, value) properties[name] = value end,
  get_commit_text = function() return "我用Python写了一个" end,
  has_menu = function() return true end,
  commit_notifier = { connect = function(_, callback)
    on_commit = callback
    return { disconnect = function() end }
  end },
}
local env = { engine = { context = context, schema = { config = {
  get_int = function(_, name) if name == "riwen/port" then return tonumber(arg[1]) or 18765 end end,
} } } }
local processor, filter = { engine = env.engine }, { engine = env.engine }
local function render()
  output = {}
  _G.yield = function(candidate) output[#output + 1] = candidate.text end
  riwen.filter.func({ iter = function()
    local i = 0
    local texts = { "城市", "程式", "诚实" }
    return function()
      i = i + 1
      if texts[i] then return { text = texts[i], type = "phrase", quality = 1, start = 0, _end = 4 } end
    end
  end }, filter)
end
context.refresh_non_confirmed_composition = render
riwen.processor.init(processor); riwen.filter.init(filter)
on_commit(context)
render()
print("Before: " .. table.concat(output, ", "))
local deadline = socket.gettime() + 2
repeat
  -- Waiting is only in this standalone demonstration, never a Rime callback.
  socket.sleep(0.02)
  riwen.processor.func({ repr = function() return "F8" end, release = function() return false end }, processor)
until processor.riwen.applied or socket.gettime() >= deadline
print("After: " .. table.concat(output, ", "))
local succeeded = processor.riwen.applied ~= nil
riwen.processor.fini(processor); riwen.filter.fini(filter)
if not succeeded then io.stderr:write("No ready ranking; check service/model latency.\n"); os.exit(1) end
