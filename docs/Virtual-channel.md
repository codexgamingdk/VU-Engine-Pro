# Optional individual virtual channel

On a separate test system, copy [90-vu-example.conf](../examples/pipewire/90-vu-example.conf) to ~/.config/pipewire/pipewire.conf.d/ and start a new audio session. Remove that one file and start a new session to uninstall it. The example declares one silent stereo sink. It contains no link or routing rules. A session manager still controls default selection and may apply local policy. Review default-device policy before enabling it.

The stable node.name identifies the selection. node.virtual and media.class describe a virtual sink, audio.position specifies stereo, and vuengine.control.role explicitly describes an individual channel. In the inspector refresh the device list and select Example audio channel. The meter will read silence until an application sends audio there. Enrollment additionally requires verifiable server, serial and volume properties. This example awaits disposable-host qualification.
