# Domoticz Stipple Plugin

Domoticz integration for [Stipple](https://github.com/galadril/Stipple)

## Supported compatibility devices

The unit numbers are intentionally inherited from the AWTRIX NG plugin.

| Unit | Domoticz device | Stipple implementation |
|---:|---|---|
| 4 | Send Notification | `POST /api/v1/notifications` |
| 5 | Send Custom App | `PUT /api/v1/apps/{id}` + activate |
| 6 | Send Settings | `PATCH /api/v1/settings` |
| 7 | Next App | `POST /api/v1/input` |
| 8 | Previous App | `POST /api/v1/input` |
| 9 | Dismiss Notification | `DELETE /api/v1/notifications` |
| 11 | Transition effect | Stipple display setting compatibility mapping |
| 12 | Overlay | Stipple display setting compatibility mapping |
| 14 | Brightness | Stipple display settings |


## Installation

Clone the repository into the Domoticz plugin directory:

```bash
cd ~/domoticz/plugins
git clone https://github.com/galadril/Domoticz-Stipple-Plugin.git
sudo systemctl restart domoticz
```

Then add the hardware in:

**Setup → Hardware → Stipple**

Configure the clock's hostname or IP address. The default is:

```text
stipple.local
```

If Stipple HTTP Basic authentication is enabled, enter the username/password in
the hardware configuration.

## Notifications

`Send Notification` intentionally accepts the same convenient formats as the.

### Plain text

Put this in the Domoticz device Description:

```text
Hello from Domoticz
```

The configured default Stipple asset ID is used as the icon.

### Icon + text shorthand

```text
39762;Washing machine is finished
```

## Requirements

- Domoticz with Python plugin support
- Python 3
- `requests`
- Stipple device reachable from the Domoticz host

Install `requests` if necessary:

```bash
python3 -m pip install requests
```

## License

GPL-3.0-or-later
