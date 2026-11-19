# Security

Only approve a key and channel you recognize. Local approvals bind the key context and control settings to the current boot, server cookie, node name, serial and bound ID. Restarts of PipeWire or Linux require fresh approval. A locally imported exact copy occupying the same host context with identical control settings cannot be distinguished from the original key. The trusted computing base includes OpenDeck, its plugins, the local audio server, channel providers and the current user account. The approval UI does not isolate malicious local software. Keep the Flatpak host bridge disabled if its broad access is unacceptable.

Report safety issues privately to the maintainer before posting logs. Use a private GitHub vulnerability report once a public repository has enabled it. Until then use your existing private contact with CodeX. Remove usernames, IDs, node names and recording data from reports.
