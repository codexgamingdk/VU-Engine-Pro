-- Transient wpexec client. Resolve exactly one proxy before touching its Props.
local input = (...):parse()
local function end_request(result)
  print(result)
  Core.quit()
end

local function node_matches(node)
  local props = node.properties
  local name = props["node.name"]
  if name ~= input.node_name or props["media.class"] ~= "Audio/Sink"
     or props["node.virtual"] ~= "true" or props["device.id"] or props["card.profile.device"] then return false end
  local individual = props["vuengine.control.role"] == "channel"
  if name:sub(1,6) == "pwctl." then
    individual = name:match("^pwctl%.source%.psou%-.+") and not name:match("%.out$")
  end
  return individual and node["bound-id"] == input.id
      and tonumber(props["object.serial"]) == input.serial
      and tonumber(Core.get_info().cookie) == input.cookie
end

local function channel_state(node)
  local state
  for param in node:iterate_params("Props") do
    local fields = param:parse().properties
    if fields.channelVolumes then
      if state then return nil end
      state = fields
    end
  end
  if not state or type(state.mute) ~= "boolean" or type(state.channelVolumes) ~= "table"
     or #state.channelVolumes ~= 2 then return nil end
  for _,gain in ipairs(state.channelVolumes) do
    if type(gain) ~= "number" or not (gain >= 0 and gain < math.huge) then return nil end
  end
  return state
end

local function write(node, key, value)
  node:set_param("Props", Pod.Object({"Spa:Pod:Object:Param:Props","Props",[key]=value}))
end

local function apply(node,state)
  local op = input.action
  if op == "mute_toggle" then return write(node,"mute",not state.mute) end
  local left,right = state.channelVolumes[1],state.channelVolumes[2]
  local maximum = math.max(left,right)
  local gain = input.value / 100
  local step = op == "volume_up" or op == "volume_down"
  local compat = step and input.unmute
  if step then
    local level = maximum ^ (1/3)
    if compat then
      level = ((left+right)/2) ^ (1/3)
      gain = math.min(gain,0.20)
      if state.mute then write(node,"mute",false) end
    end
    if op == "volume_up" then gain = math.min(1,level+gain)
    elseif compat then gain = math.max(0,math.min(1.5,level-gain))
    else gain = math.max(0,math.min(1,level)-gain) end
  end
  local power = gain^3
  local l,r = power,power
  if not compat and maximum > 0 then l,r = power*(left/maximum),power*(right/maximum) end
  write(node,"channelVolumes",Pod.Array({"Spa:Float",l,r}))
end

local supported = {inspect=true,mute_toggle=true,volume_up=true,volume_down=true,set_volume=true,reset_volume=true}
if type(input) ~= "table" or not supported[input.action] or type(input.node_name) ~= "string"
   or #input.node_name < 1 or #input.node_name > 256 or type(input.id) ~= "number"
   or type(input.serial) ~= "number" or type(input.cookie) ~= "number"
   or type(input.unmute) ~= "boolean" or type(input.value) ~= "number"
   or not (input.value >= 0 and input.value <= 100) then return end_request("Invalid request") end

local registry = ObjectManager {Interest {type="node",Constraint {"node.name","=",input.node_name}}}
registry:connect("installed",function()
  local selected
  for candidate in registry:iterate() do
    if selected then return end_request("Ambiguous target") end
    selected = candidate
  end
  if not selected or not node_matches(selected) then return end_request("Identity unavailable") end
  local state = channel_state(selected)
  if not state then return end_request("Stereo controls unavailable") end
  if input.action == "inspect" then return end_request("VU_OK") end
  apply(selected,state)
  Core.sync(function(error_message) end_request(error_message or "VU_OK") end)
end)
registry:activate()
