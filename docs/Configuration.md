# Configuration

**Audio Meter Source** lists uniquely named Audio/Source nodes and Audio/Sink monitors. Select the endpoint carrying the signal of interest. Multiple keys using that source share one capture while their meter is visible.

**Volume Control Target** lists eligible individual stereo virtual sinks. Inspect both the description and technical name. A generic channel provider can identify a dedicated virtual sink with the node property `vuengine.control.role = channel`. The plugin reads this declaration. It does not add the property, create a sink, or configure routing. Existing individual PipeWire Controller sink names also have a compatibility path. All identity, virtual-device and stereo checks still apply.

**Control Action** offers meter only, gain up/down, mute toggle, set volume and reset to a configured volume. Choose the preset or custom step. Optional unmute on a step uses the compatibility range of 1–20 points and unmutes before setting the gain. A boosted 115% channel can step down to 110% with a five-point compatibility step. Upward steps are capped at 100%.

**Approve volume control** after configuring the key. Approval binds the host key context and control settings to the reviewed device instance. Use **Revoke approval** to disable writes immediately. A new key context or changed control configuration requires approval. Appearance changes preserve approval. Revocation removes every binding for that channel. Metering needs none.

**Appearance** controls the custom label, theme, accent, layout, VU and percentage visibility, peak marker, status, icon and meter style. For a percentage key use Balanced with Show VU Meter off and Show Volume Percentage on. Reverse those options for its mute companion.

[Basic Meter](../example-profiles/Basic%20Meter.json) contains one unbound meter. [Clean Layout](../example-profiles/Clean%20Layout.json) contains three unbound keys. These are OpenDeck profile JSON templates. Import portability has not been qualified. Alternatively recreate their settings on blank keys and select local endpoints.
