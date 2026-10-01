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
