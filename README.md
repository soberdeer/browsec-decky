# Browsec Decky

An unofficial Browsec VPN for Decky Loader.

- complete IPv4 and IPv6 Game Mode traffic through the VPN
- official Browsec Premium account authentication and server list
- location selection, connect, disconnect, IP verification, and sign-out

**Requires Premium account!** It's a dependency Browsec requirement.

## Security model

Decky runs the backend with the `_root` flag because creating the TUN
interface and routes requires network-administration privileges. The plugin:

- keeps the password only for the duration of the sign-in request;
- never returns tokens, UUIDs, server IPs, or `xsni` values to the frontend;
- verifies exact SHA-256 hashes for the official runtime at build time and
  before every connection;
- writes generated VPN configuration with mode `0600`;
- refuses to connect while Browsec Desktop appears to be running;
- tears down both subprocess groups when disconnected or unloaded; and
- verifies that the external IP changed before reporting `Protected`.

There is no kill switch yet. A tunnel process that fails unexpectedly can
restore ordinary network routing.

## Build

Requirements: Node.js 20+, Corepack, Python 3.11+, `ar`, `tar`, `zip`, and
standard SHA-256 tools.

```sh
corepack pnpm install --frozen-lockfile
corepack pnpm run verify
./scripts/import-runtime.sh /path/to/browsec-desktop_1.2.2_amd64.deb
corepack pnpm run package
```

Omit the `.deb` argument to download the exact official package. The import
script verifies the package and both extracted executables. Runtime binaries
are intentionally excluded from Git.

The installable ZIP and SHA-256 file are created in `out/`.

## Install for testing

Enable developer mode in Decky Loader, choose **Install Plugin from ZIP**, and
select `Browsec-Decky-<version>.zip`. Because this is a root plugin, review the
source and install only a release you trust.

Do not run Browsec Desktop and Browsec Decky simultaneously.

## License

Project-authored code is source-available freeware under
[LICENSE](LICENSE). Third-party components and Browsec materials are covered
by [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES) and their respective terms.
