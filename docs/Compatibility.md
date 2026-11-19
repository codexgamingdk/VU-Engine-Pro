# Compatibility

| PipeWire endpoint | Meter | Write eligibility |
|---|---|---|
| Dedicated virtual stereo sink | Sink monitor | Recognized individual channel, explicit local approval and bound-proxy checks |
| Virtual source | Source | Read only |
| Physical output | Sink monitor | Read only |
| Hardware microphone | Source | Read only |
| Application playback or recording stream | No direct selection | Unsupported |
| PipeWire Controller individual channel | Sink monitor when exposed as Audio/Sink | Same identity, stereo and permission requirements |
| Other virtual sinks, mixes and Controller buses | Sink monitor | Read only without an eligible individual-channel declaration. Controller buses are protected |

A virtual sink must expose node.virtual=true, usable stereo channelVolumes and mute, a unique node.name, object.serial and a server cookie. Device-backed sinks are rejected. Eligibility relies on accurate metadata from a trusted local channel provider. A label alone cannot classify a generic virtual mix.

| Environment | Evidence |
|---|---|
| Bazzite x86_64, OpenDeck 2.14.2 Flatpak, Stream Deck Original V2 | Prior production versions physically exercised. Community control backend tested offline only |
| Native Linux x86_64 | Command selection tested with mocks. Runtime qualification pending |
| Fedora, Debian, Ubuntu, Mint, Arch, openSUSE | Candidates if runtime requirements are met. No distro acceptance test |
| ARM64 | No declared target triple or qualification |

Control needs WirePlumber's wpexec with the [Lua core API](https://pipewire.pages.freedesktop.org/wireplumber/scripting/lua_api/lua_core_api.html), node object management, SPA Props and bound proxy parameter writes. No PipeWire Controller installation, OBS, external mixer or Python package is required. Missing host access disables writes. Available tools alone do not establish compatibility.
