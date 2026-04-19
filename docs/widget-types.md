# Widget Types Reference

This document is a practical reference for Umbrel widget shapes we can build against in
TunnelSats.

Important:
- Common widget-level fields seen across shapes are `type`, `link`, `refresh`, and shape-specific fields such as `items`, `buttons`, `progress`, or `count`.
- The type name `two-stats-with-guage` is intentionally spelled `guage` because that is the working type name used in real examples.
- This page is based on verified current Umbrel source plus the official `getumbrel/umbrel-apps` manifests checked on April 18, 2026.

## Verified support

General app widget types currently implemented by Umbrel itself:
- `text-with-buttons`
- `text-with-progress`
- `two-stats-with-guage`
- `three-stats`
- `four-stats`
- `list`
- `list-emoji`

Currently used in official `getumbrel/umbrel-apps` manifests:
- `text-with-buttons`
- `text-with-progress`
- `three-stats`
- `four-stats`
- `list`
- `list-emoji`

Implemented by Umbrel, but not currently used in the official app-store manifests we checked:
- `two-stats-with-guage`

Not present in current Umbrel widget type definitions:
- `text`
- `simple-list`

## Current active shapes

### `three-stats`

Observed in the current `tunnel-status` widget.

Shape:

```json
{
  "type": "three-stats",
  "link": "",
  "refresh": "5s",
  "items": [
    { "subtext": "Peers", "text": "5" },
    { "subtext": "Channels", "text": "3" },
    { "subtext": "Tunnel", "text": "🟢" }
  ]
}
```

Notes:
- Each item uses `subtext` + `text`
- No `title`

### `four-stats`

Observed in current `tunnel-overview` work and older preview widgets.

Shape:

```json
{
  "type": "four-stats",
  "link": "",
  "refresh": "5s",
  "items": [
    { "title": "Tunnel", "text": "🟢" },
    { "title": "Protected", "text": "🟢" },
    { "title": "Expires", "text": "May 4 2026" },
    { "title": "Node", "text": "LND" }
  ]
}
```

Notes:
- Each item uses `title` + `text`
- Historical versions in this repo also used optional `subtext` per item

## Additional widget shapes

### `text-with-buttons`

Observed in wallet-style widgets.

Shape:

```json
{
  "type": "text-with-buttons",
  "link": "",
  "refresh": "5s",
  "title": "Bitcoin Wallet",
  "text": "1,845,894",
  "subtext": "sats · Tunnel Protected (LND)",
  "buttons": [
    { "text": "Withdraw", "icon": "arrow-up-right", "link": "?action=send-bitcoin" },
    { "text": "Deposit", "icon": "arrow-down-right", "link": "?action=receive-bitcoin" }
  ]
}
```

Notes:
- Top-level `title`, `text`, and optional `subtext`
- `buttons` is an array of `{text, icon, link}`

### `text-with-progress`

Observed in preview-style status widgets.

Shape:

```json
{
  "type": "text-with-progress",
  "link": "",
  "refresh": "5s",
  "title": "Tunnel status",
  "text": "🟢 Tunnel Protected (LND)",
  "subtext": "Node: LND",
  "progressLabel": "Protected",
  "progress": 1
}
```

Notes:
- Single-card text widget with a progress bar
- Uses top-level `progressLabel` and numeric `progress`

### `two-stats-with-guage`

Observed in two-card preview widgets.

Shape:

```json
{
  "type": "two-stats-with-guage",
  "link": "",
  "refresh": "5s",
  "items": [
    {
      "title": "Channels",
      "text": "3",
      "subtext": "active",
      "progress": 0.15
    },
    {
      "title": "Tunnel",
      "text": "🟢 Tunnel Protected (LND)",
      "subtext": "Node: LND",
      "progress": 1
    }
  ]
}
```

Notes:
- Two-item layout
- Each item carries its own `progress`
- Spelling is `guage`, not `gauge`

### `list`

Observed in row-list style widgets.

Shape:

```json
{
  "type": "list",
  "link": "",
  "refresh": "5s",
  "items": [
    { "text": "Tunnel", "subtext": "🟢 Tunnel Protected (LND)" },
    { "text": "Peers", "subtext": "5" },
    { "text": "Channels", "subtext": "3" },
    { "text": "Outbound", "subtext": "90K" }
  ],
  "noItemsText": "No tunnel stats"
}
```

Notes:
- Row list using `text` + `subtext`
- Historical examples also used `noItemsText`

### `list-emoji`

Observed in emoji list widgets.

Shape:

```json
{
  "type": "list-emoji",
  "link": "",
  "refresh": "5s",
  "count": "4",
  "items": [
    { "emoji": "🛡️", "text": "🟢 Tunnel Protected (LND)" },
    { "emoji": "🤝", "text": "Peers: 5" },
    { "emoji": "⚡", "text": "Channels: 3" },
    { "emoji": "📤", "text": "Outbound: 90K" }
  ]
}
```

Notes:
- Uses top-level `count`
- Each item uses `emoji` + `text`

## Known widget types

Widget shapes documented here:
- `text-with-buttons`
- `text-with-progress`
- `two-stats-with-guage`
- `three-stats`
- `four-stats`
- `list`
- `list-emoji`

## Upstream references

Useful upstream code and manifest references:
- `getumbrel/umbrel`: `packages/ui/src/modules/widgets/shared/constants.ts`
- `getumbrel/umbrel`: `packages/ui/src/modules/widgets/index.tsx`
- `getumbrel/umbrel`: `packages/ui/src/modules/widgets/two-stats-with-guage-widget.tsx`
- `getumbrel/umbrel-apps`: examples in `lightning/umbrel-app.yml`, `bitcoin/umbrel-app.yml`, `nostr-relay/umbrel-app.yml`, and `datum/umbrel-app.yml`
