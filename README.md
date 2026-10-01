# Matrix for Home Assistant (fork)

A fork of Home Assistant's built-in [Matrix integration](https://www.home-assistant.io/integrations/matrix/),
installed through HACS. It uses the same `matrix` domain, so it **replaces** the
built-in integration: the `matrix:` and `notify:` configuration, the
`matrix.send_message` and `matrix.react` actions and `notify.<name>` keep working
unchanged.

Based on Home Assistant Core 2026.9.4.

## Why

Fixes and features here do not have to wait for a Core release.

## Changes from Core

- **HTML messages carry a plain text `body`.** Core sends the HTML string as both
  `body` and `formatted_body`. The Matrix spec says `body` should be the plain
  text version, so clients and notifications that display `body` showed raw
  tags. Tags are now removed, entities decoded, and line breaks and block
  elements turned into newlines.

- **End-to-end encryption.** In an encrypted room, messages and images are sent
  encrypted and incoming commands are decrypted. Unencrypted rooms work as
  before. See [Encryption](#encryption).
- **Room IDs without a server part** (room version 12) are accepted.
- **Nothing is sent until startup has finished**, and a room the bot is not in
  is refused with an error instead of being attempted.

## Encryption

Encryption is automatic: if a room is encrypted, the bot encrypts.

**What it protects.** Messages and images are stored encrypted on the
homeserver, in its media store and in its backups. It does not protect against
someone who controls the homeserver or a room member's account: the bot sends to
every device in the room without verifying it, because an unattended bot has
nobody to do the verifying.

**What you will see.** The bot's device is not cross-signed, so clients mark it
as unverified. A client set to never send to unverified sessions will not send
it commands.

**Where the keys live.** `.matrix_store/` in the Home Assistant configuration
directory holds the device's keys, and `.matrix.conf` its access token and
device ID. Both are included in Home Assistant backups, and the keys are not
encrypted on disk.

**It fails closed.** If encryption cannot be set up (dependencies missing, key
store unreadable, a login with no device), messages to encrypted rooms are
refused with an error in the log. They are never sent in the clear.

**Devices.** The bot keeps one device across restarts and across a password
login after its token expired. A device whose keys are not on disk is logged
out and replaced by a new one. This happens once when upgrading from a version
without encryption, and again if `.matrix_store/` is ever lost.

**Reactions** are sent unencrypted, as the Matrix protocol defines them.

## Installation

1. In HACS, add `https://github.com/dn5qMDW3/ha-matrix` as a custom repository
   of type *Integration*.
2. Download **Matrix** and restart Home Assistant.

Home Assistant logs a warning that a custom integration overrides a built-in
one. That is expected.

To go back to the built-in integration, remove this one in HACS and restart.

## Keeping up with Core

Overriding a built-in integration means Core's own changes to `matrix` no longer
reach you. They have to be merged into this repository by hand.

## Configuration

See the [Core documentation](https://www.home-assistant.io/integrations/matrix/).

## License

Apache License 2.0, the same as Home Assistant Core, from which this code is
derived. See [LICENSE](LICENSE).
