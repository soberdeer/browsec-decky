# Browsec Decky

![Browsec × Decky Loader](assets/header.svg)

An unofficial Browsec VPN for Decky Loader.


- complete IPv4 and IPv6 Game Mode traffic through the VPN
- official Browsec Premium account authentication and server list
- location selection, connect, disconnect, IP verification, and sign-out
- a mandatory nftables kill switch for every VPN connection

**Requires Premium account!** It's a dependency Browsec requirement.

Need a version for Desktop Mode? Check out [Browsec Deck](https://github.com/soberdeer/browsec-deck).

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
