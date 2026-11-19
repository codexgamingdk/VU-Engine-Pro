-- Run the production helper against a private mock registry and a recording proxy.
local helper = assert(loadfile("plugin/org.codex.vuengine.sdPlugin/native_step.lua"))
local function test(action, value, volume, muted, unmute, change)
  local writes, message = {}, ""
  local request = {node_name="example.channel", action=action, value=value, unmute=unmute,
                   id=9, serial=97, cookie=301}
  local node = {properties={["media.class"]="Audio/Sink", ["node.virtual"]="true",
               ["node.name"]=request.node_name, ["object.serial"]="97", ["vuengine.control.role"]="channel"},
               ["bound-id"]=9}
  local nodes, cookie = {node}, 301
  if change == "serial" then node.properties["object.serial"]="109"
  elseif change == "cookie" then cookie=302
  elseif change == "missing" then nodes={}
  elseif change == "ambiguous" then nodes={node,node}
  elseif change == "hardware" then node.properties["device.id"]="3"
  elseif change == "master" then request.node_name="pwctl.vd-master"
  elseif change == "unmarked" then node.properties["vuengine.control.role"]=nil end
  local function iterator(list)
    local i=0
    return function() i=i+1;return list[i] end
  end
  function node:iterate_params()
    return iterator({{parse=function() return {properties={channelVolumes={volume^3,volume^3},mute=muted}} end}})
  end
  function node:set_param(_,pod) table.insert(writes,pod) end
  Core={get_info=function() return {cookie=cookie} end,quit=function() end,sync=function(fn) fn() end}
  local function passthrough(x) return x end
  Interest,Constraint=passthrough,passthrough
  Pod={Object=passthrough,Array=passthrough}
  ObjectManager=function()
    return {iterate=function() return iterator(nodes) end, connect=function(self,_,fn) self.callback=fn end,
            activate=function(self) self.callback() end}
  end
  local oldprint=print
  print=function(s) message=s end
  helper({parse=function() return request end})
  print=oldprint
  return message,writes
end
for _, change in ipairs({"serial","cookie","missing","ambiguous","hardware","master","unmarked"}) do
  local msg,w=test("volume_up",5,.5,false,false,change)
  assert(msg~="VU_OK" and #w==0,change)
end
for _,c in ipairs({{"volume_up",5,.98,false,false,1},{"volume_down",5,.02,false,false,0},
                   {"volume_down",5,1.15,true,true,1.10},{"set_volume",75,.2,false,false,.75},
                   {"reset_volume",65,.5,true,false,.65}}) do
  local msg,w=test(c[1],c[2],c[3],c[4],c[5])
  assert(msg=="VU_OK" and math.abs(w[#w].channelVolumes[2]-c[6]^3)<1e-7)
  if c[5] then assert(#w==2 and w[1].mute==false) else assert(#w==1) end
end
for _,muted in ipairs({false,true}) do
  local msg,w=test("mute_toggle",0,.5,muted,false)
  assert(msg=="VU_OK" and w[1].mute==not muted)
end
local msg,w=test("inspect",0,.5,false,false)
assert(msg=="VU_OK" and #w==0)
print("Bound proxy fixtures passed")
