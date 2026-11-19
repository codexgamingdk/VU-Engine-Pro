# Troubleshooting

- **Empty source list** — Check PipeWire connectivity and availability of pw-dump and pw-cat inside the OpenDeck runtime. Duplicate names are excluded. Raw application streams do not appear.
- **Source appears but target does not** — Inspect the endpoint class and individual-channel declaration. Hardware and unclassified sinks are intentionally read-only.
- **Approval required again** — Review the local target and approve the current key after changing control settings, moving to a new key context or reconnecting a device. Serial and core changes invalidate the permission.
- **Cannot run wpexec** — For native installs check its PATH and WirePlumber scripting support. In Flatpak check the host bridge, helper visibility and host executable. Meter-only operation does not need the helper.
- **Silent bar** — An idle source has an empty meter. OFFLINE indicates loss of availability. Check the selected source, independent control target, Show VU Meter and external mute state.
