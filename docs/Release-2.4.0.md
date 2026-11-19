# VU Engine Pro 2.4.0 – Community Edition

Tag `v2.4.0` · Pre-release · Developer CodeX

Your audio. Your control.

Advanced real-time audio metering and volume controls for OpenDeck on Linux, powered by PipeWire.

Place stereo RMS and peak meters, volume steps, mute, set volume and reset controls on individual keys. Clean Layout separates gain percentages from signal activity. Visible meters share capture processes. Each writable control requires local approval.

## Requirements and installation

Linux x86_64, OpenDeck, Python 3.10+, access to PipeWire and the pw-cat and pw-dump commands are required. Optional control needs WirePlumber wpexec. Native installations invoke it directly. Flatpak installations require a usable host bridge and a host-readable helper. PipeWire Controller is optional.

Download VU-Engine-Pro-2.4.0-linux.zip and VU-Engine-Pro-2.4.0-linux.zip.sha256 together. Run `sha256sum -c VU-Engine-Pro-2.4.0-linux.zip.sha256`, then choose the ZIP in OpenDeck's local plugin installer. Back up an existing bundle with the same ID before upgrading.

## Compatibility and limits

Community Edition has only been validated offline. Keep this release marked as a pre-release until installation has been verified in a separate environment. Ordinary sources and sink monitors support metering. Writable targets are limited to verified individual stereo virtual sinks. Physical devices are read-only and direct application-stream control is unsupported. A new device instance, boot or audio server requires fresh approval. Native and Flatpak installation and physical hardware operation await qualification.

Original contributions are MIT-licensed. Bundled websockets 16.0 retains BSD-3-Clause and its upstream notice.
