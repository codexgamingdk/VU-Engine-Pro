# Installing the candidate

Use a disposable Linux account or host for release qualification. The bundle shares its identity with earlier versions. Back up OpenDeck's plugin directory and profiles before replacing an existing version.

1. Obtain the matching Linux ZIP and SHA-256 sidecar from the candidate build. In their directory run `sha256sum -c VU-Engine-Pro-2.4.0-linux.zip.sha256`.
2. In OpenDeck's Plugins view choose installation from a local plugin file and select the ZIP. The archive contains one top-level org.codex.vuengine.sdPlugin directory with an executable Python entry point.
3. Add a meter key to a blank profile. See [Configuration](Configuration.md).

For native execution the plugin requires /usr/bin/python3 and commands pw-cat and pw-dump in its environment. Optional control requires wpexec on PATH. Flatpak must expose the PipeWire socket and both metering commands to its runtime. Control additionally needs flatpak-spawn, permission to talk to org.freedesktop.Flatpak and host wpexec with read access to the helper at the supplied path. The host bridge grants broad execution power. Select metering only if that access is unsuitable. The plugin never grants permissions or installs tools.

To roll back, close OpenDeck in the disposable environment and restore its previous plugin bundle and profiles from the same backup. Local approvals live in the runtime XDG state directory under vu-engine-pro/approvals.json. Exclude that file from profiles and release packages.

## Building the archive

Run `python3 scripts/package.py`. The sorted file allowlist, fixed timestamps and normalized Unix permissions make the archive reproducible. Compare two builds using `cmp`. The ZIP contains the runtime and inspector. The repository provides guides, examples and tests separately.

The remediated package requires Python 3.10 or newer and includes its WebSocket transport and third-party license. No additional Python package installation is needed.
