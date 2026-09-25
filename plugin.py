"""
<plugin key="STIPPLE" name="Stipple" author="Mark Heinis" version="1.0.3" wikilink="https://github.com/galadril/Stipple" externallink="https://github.com/galadril/Stipple">
    <description>
        <h2>Stipple Plugin</h2><br/>
        Integrates Stipple firmware with Domoticz while keeping the supported
        Domoticz devices compatible with the AWTRIX NG plugin.<br/>
        <p>
        Notification and custom-app payloads are entered in the device
        <b>Description</b>, just like the AWTRIX NG plugin.
        </p>
    </description>
    <params>
        <param field="Address" label="IP Address / Hostname" width="200px" required="true" default="stipple.local"/>
        <param field="Username" label="Username" width="200px" required="false" default=""/>
        <param field="Password" label="Password" width="200px" required="false" default="" password="true"/>
        <param field="Mode1" label="Default Stipple Asset ID" width="150px" required="false" default="39762"/>
        <param field="Mode6" label="Debug" width="200px">
            <options>
                <option label="None" value="0" default="true"/>
                <option label="Python Only" value="2"/>
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import copy
import json
import re
import requests
from requests.auth import HTTPBasicAuth

# ---------------------------------------------------------------------------
# Compatibility contract
#
# Unit numbers intentionally match Domoticz-AWTRIXNG-Plugin.
# Unsupported AWTRIX-only devices are deliberately NOT created, but their
# numbers remain reserved so future additions cannot accidentally rewire an
# existing dzVents automation.
# ---------------------------------------------------------------------------

UNIT_POWER = 1                  # display.power
UNIT_LUX = 2                    # unsupported by Stipple
UNIT_TEMPHUM = 3                # unsupported by Stipple
UNIT_NOTIFICATION = 4
UNIT_CUSTOMAPP = 5
UNIT_SETTINGS = 6
UNIT_NEXTAPP = 7              # /input {"control":"right"}
UNIT_PREVAPP = 8              # /input {"control":"left"}
UNIT_DISMISS = 9
UNIT_RTTTL = 10                 # unsupported by Stipple
UNIT_TRANSITION = 11
UNIT_OVERLAY = 12
UNIT_TEXTCOLOR = 13             # reserved until Stipple exposes a global equivalent
UNIT_BRIGHTNESS = 14
UNIT_SLEEP = 15                 # unsupported by current Stipple API
# 16 retired in AWTRIX NG; do not reuse.
UNIT_MOODLIGHT = 17             # unsupported
UNIT_INDICATOR1 = 18            # unsupported
UNIT_INDICATOR2 = 19            # unsupported
UNIT_INDICATOR3 = 20            # unsupported
UNIT_CLOCKLAYOUT = 21           # not mapped yet
UNIT_SCROLL = 22                # not mapped yet
UNIT_AUTOTRANSITION = 23        # apps.transitions

DEFAULT_APP_NAME = "Domoticz"
DEFAULT_ICON_ID = "39762"

# Stipple-native settings exposed by the Web UI.
# Selector order is now the Stipple order; these values map directly to the
# settings API instead of pretending unsupported AWTRIX effects exist.
TRANSITION_NAMES = ["Slide", "Fade", "Wipe", "Dissolve", "Cut"]
TRANSITION_VALUES = ["slide", "fade", "wipe", "dissolve", "none"]

OVERLAY_NAMES = [
    "None", "Rain", "Snow", "Storm", "Frost",
    "Fog", "Stars", "Sparkle", "Confetti"
]
OVERLAY_VALUES = [
    "none", "rain", "snow", "storm", "frost",
    "fog", "stars", "sparkle", "confetti"
]


def selectorOptions(names, offHidden=False):
    return {
        "LevelActions": "|" * (len(names) - 1),
        "LevelNames": "|".join(names),
        "LevelOffHidden": "true" if offHidden else "false",
        "SelectorStyle": "1",
    }


class BasePlugin:
    def __init__(self):
        self.baseUrl = ""
        self.auth = None
        self.iconId = DEFAULT_ICON_ID
        self.failures = 0
        self.skipTicks = 0

    # ---------------------------------------------------------------- start

    def onStart(self):
        debugLevel = int(Parameters.get("Mode6", "0"))
        if debugLevel > 0:
            Domoticz.Debugging(debugLevel)

        self.baseUrl = "http://{}/api/v1".format(
            Parameters["Address"].strip().rstrip("/")
        )
        self.iconId = (Parameters.get("Mode1", "") or DEFAULT_ICON_ID).strip()

        if Parameters.get("Username"):
            self.auth = HTTPBasicAuth(
                Parameters["Username"],
                Parameters.get("Password", "")
            )

        Domoticz.Log("Stipple plugin started")
        self.createDevices()
        Domoticz.Heartbeat(30)

    def onStop(self):
        Domoticz.Log("Stipple plugin stopped")

    # --------------------------------------------------------------- devices

    def createDevices(self):
        # No custom Domoticz image archive is used by this plugin.
        #
        # The device names/types/units below intentionally mirror the supported
        # subset of Domoticz-AWTRIXNG-Plugin.

        if UNIT_POWER not in Devices:
            Domoticz.Device(
                Name="Power",
                Unit=UNIT_POWER,
                TypeName="Switch"
            ).Create()

        if UNIT_NOTIFICATION not in Devices:
            Domoticz.Device(
                Name="Send Notification",
                Unit=UNIT_NOTIFICATION,
                Type=244, Subtype=73, Switchtype=9,
                Description="Enter notification text here"
            ).Create()

        if UNIT_CUSTOMAPP not in Devices:
            Domoticz.Device(
                Name="Send Custom App",
                Unit=UNIT_CUSTOMAPP,
                Type=244, Subtype=73, Switchtype=9,
                Description="Enter custom app text here"
            ).Create()

        if UNIT_SETTINGS not in Devices:
            Domoticz.Device(
                Name="Send Settings",
                Unit=UNIT_SETTINGS,
                Type=244, Subtype=73, Switchtype=9,
                Description='{"display":{"brightness":128}}'
            ).Create()

        if UNIT_NEXTAPP not in Devices:
            Domoticz.Device(
                Name="Next App",
                Unit=UNIT_NEXTAPP,
                Type=244, Subtype=73, Switchtype=9,
                Description="Advance to the next app"
            ).Create()

        if UNIT_PREVAPP not in Devices:
            Domoticz.Device(
                Name="Previous App",
                Unit=UNIT_PREVAPP,
                Type=244, Subtype=73, Switchtype=9,
                Description="Go back to the previous app"
            ).Create()

        if UNIT_DISMISS not in Devices:
            Domoticz.Device(
                Name="Dismiss Notification",
                Unit=UNIT_DISMISS,
                Type=244, Subtype=73, Switchtype=9,
                Description="Dismiss notifications"
            ).Create()

        if UNIT_TRANSITION not in Devices:
            Domoticz.Device(
                Name="Transition effect",
                Unit=UNIT_TRANSITION,
                TypeName="Selector Switch",
                Options=selectorOptions(TRANSITION_NAMES, False)
            ).Create()

        if UNIT_OVERLAY not in Devices:
            Domoticz.Device(
                Name="Overlay",
                Unit=UNIT_OVERLAY,
                TypeName="Selector Switch",
                Options=selectorOptions(OVERLAY_NAMES, False)
            ).Create()

        if UNIT_BRIGHTNESS not in Devices:
            Domoticz.Device(
                Name="Brightness",
                Unit=UNIT_BRIGHTNESS,
                TypeName="Dimmer"
            ).Create()

        if UNIT_AUTOTRANSITION not in Devices:
            Domoticz.Device(
                Name="Auto Transition",
                Unit=UNIT_AUTOTRANSITION,
                TypeName="Switch"
            ).Create()

    # ---------------------------------------------------------------- HTTP

    def _request(self, method, path, jsonBody=None):
        url = self.baseUrl + path

        try:
            response = requests.request(
                method,
                url,
                json=jsonBody,
                auth=self.auth,
                timeout=5
            )

            Domoticz.Debug(
                "{} {} {} -> {}".format(
                    method,
                    url,
                    jsonBody if jsonBody is not None else "",
                    response.status_code
                )
            )

            if response.status_code >= 300:
                message = response.text
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        error = body.get("error")
                        if isinstance(error, dict):
                            message = "{}: {}".format(
                                error.get("code", "error"),
                                error.get("message", "")
                            ).strip(": ")
                except ValueError:
                    pass

                Domoticz.Error(
                    "Stipple request failed: {} {} -> {} {}".format(
                        method, url, response.status_code, message
                    )
                )
                return None

            if not response.text:
                return True

            try:
                return response.json()
            except ValueError:
                return response.text

        except Exception as e:
            Domoticz.Error(
                "Stipple request exception: {} {} -> {}".format(
                    method, url, str(e)
                )
            )
            return None

    # -------------------------------------------------------------- helpers

    def description(self, unit):
        try:
            return (Devices[unit].Description or "").strip()
        except Exception:
            return ""

    def payloadText(self, unit):
        """
        AWTRIX automations normally put their payload in Description.
        Keep a small sValue fallback because some dzVents setups update the
        device value rather than editing Description.
        """
        message = self.description(unit)
        if message:
            return message

        try:
            return (Devices[unit].sValue or "").strip()
        except Exception:
            return ""

    def parsePushMessage(self, message):
        """
        AWTRIX-compatible input:
          {"icon":39762,"text":"Hello"}
          39762;Hello
          Hello
        """
        message = (message or "").strip()
        if not message:
            return None

        if message.startswith("{") or message.startswith("["):
            try:
                return json.loads(message)
            except ValueError:
                Domoticz.Error("Invalid JSON payload: {}".format(message))
                return None

        if ";" in message:
            icon, text = message.split(";", 1)
            return {"icon": icon.strip(), "text": text.strip()}

        return {"icon": self.iconId, "text": message}

    @staticmethod
    def normaliseIcons(payload):
        # Stipple asset IDs are strings. Preserve compatibility with dzVents
        # scripts that encode AWTRIX icon IDs as JSON numbers.
        entries = payload if isinstance(payload, list) else [payload]
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            icon = entry.get("icon")
            if isinstance(icon, bool):
                continue
            if isinstance(icon, (int, float)):
                entry["icon"] = str(int(icon))

        return payload

    @staticmethod
    def sanitizeAppId(value):
        value = str(value or DEFAULT_APP_NAME)
        value = value.lower()
        value = re.sub(r"[^a-z0-9_-]", "-", value)
        value = re.sub(r"-+", "-", value).strip("-_")
        return (value or "domoticz")[:32]

    def customAppName(self, payload):
        entries = payload if isinstance(payload, list) else [payload]

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            appname = entry.get("appname")
            if appname:
                return self.sanitizeAppId(appname)

            app_id = entry.get("id")
            if app_id:
                return self.sanitizeAppId(app_id)

        return "domoticz"

    @staticmethod
    def awtrixElementToStipple(entry):
        """
        Translate the common AWTRIX pushed-app fields into a simple Stipple
        scene. Unknown fields are intentionally ignored instead of being sent
        as undocumented Stipple properties.

        Native Stipple AppWrite JSON can also be supplied; see sendCustomApp().
        """
        elements = []

        icon = entry.get("icon")
        text = entry.get("text")

        if icon is not None:
            elements.append({
                "type": "icon",
                "id": str(icon),
                "x": 0,
                "y": 4
            })

        if text is not None:
            elements.append({
                "type": "text",
                "text": str(text),
                "x": 10 if icon is not None else 0,
                "y": 4
            })

        # Preserve a few useful concepts when present. The exact scene renderer
        # owns their interpretation; these are only emitted for obvious common
        # AWTRIX fields.
        if "progress" in entry:
            try:
                progress = max(0, min(int(entry["progress"]), 100))
                elements.append({
                    "type": "progress",
                    "value": progress,
                    "x": 0,
                    "y": 14,
                    "width": 52
                })
            except (TypeError, ValueError):
                pass

        return {"elements": elements}

    # --------------------------------------------------------- notifications

    def notificationPayload(self, entry):
        """
        Convert common AWTRIX notification fields to the documented Stipple
        notification schema. Native Stipple names pass through.
        """
        if not isinstance(entry, dict):
            return None

        src = copy.deepcopy(entry)
        out = {}

        # Directly compatible fields.
        for key in (
            "id", "text", "priority", "durationSeconds",
            "hold", "dismissible", "sound", "icon"
        ):
            if key in src:
                out[key] = src[key]

        # AWTRIX compatibility aliases.
        if "durationSeconds" not in out:
            if "duration" in src:
                try:
                    # AWTRIX commonly expresses duration in seconds.
                    out["durationSeconds"] = max(0, int(src["duration"]))
                except (TypeError, ValueError):
                    pass

        if "hold" not in out and "hold" in src:
            out["hold"] = bool(src["hold"])

        if "icon" in out and isinstance(out["icon"], (int, float)) and not isinstance(out["icon"], bool):
            out["icon"] = str(int(out["icon"]))

        return out

    def sendNotification(self, payload):
        if payload is None:
            return

        payload = self.normaliseIcons(payload)
        entries = payload if isinstance(payload, list) else [payload]

        # Stipple's API queues one notification object per POST. AWTRIX payload
        # arrays are therefore sent one by one in their original order.
        for entry in entries:
            converted = self.notificationPayload(entry)
            if not converted:
                Domoticz.Error("Notification payload must be a JSON object")
                continue
            self._request("POST", "/notifications", converted)

    # -------------------------------------------------------------- apps

    def nativeStippleApp(self, payload):
        """
        Recognise a native Stipple AppWrite payload. This allows advanced users
        to bypass AWTRIX translation while keeping the same Domoticz button.
        """
        return (
            isinstance(payload, dict)
            and "scene" in payload
            and (
                "id" in payload
                or "name" in payload
                or "enabled" in payload
                or "durationSeconds" in payload
            )
        )

    def sendCustomApp(self, payload):
        if payload is None:
            return

        payload = self.normaliseIcons(payload)

        if self.nativeStippleApp(payload):
            app = copy.deepcopy(payload)
            app_id = self.sanitizeAppId(app.pop("id", "domoticz"))
            app.setdefault("name", app_id)
            app.setdefault("enabled", True)
            self._request("PUT", "/apps/{}".format(app_id), app)
            return

        entries = payload if isinstance(payload, list) else [payload]
        app_id = self.customAppName(payload)

        # A pushed AWTRIX app can be one object or a list of page-like objects.
        # Translate each entry into scene elements and concatenate them.
        elements = []
        duration = None

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            scene = self.awtrixElementToStipple(entry)
            elements.extend(scene.get("elements", []))

            if duration is None:
                raw_duration = entry.get("durationSeconds", entry.get("duration"))
                if raw_duration is not None:
                    try:
                        duration = max(0, int(raw_duration))
                    except (TypeError, ValueError):
                        pass

        app = {
            "name": app_id,
            "enabled": True,
            "scene": {"elements": elements}
        }
        if duration is not None:
            app["durationSeconds"] = duration

        result = self._request("PUT", "/apps/{}".format(app_id), app)
        if result is not None:
            # Pushed apps are expected to become visible immediately.
            self._request("POST", "/apps/{}/activate".format(app_id))

    # ----------------------------------------------------------- settings/UI

    def sendSettings(self, message):
        """
        Optional escape hatch for Stipple-native settings.

        Unlike the AWTRIX plugin, this method does NOT pretend AWTRIX settings
        keys are Stipple settings. The JSON is sent as a native Stipple
        Settings PATCH.
        """
        try:
            payload = json.loads(message)
        except ValueError:
            Domoticz.Error("Invalid settings JSON: {}".format(message))
            return

        if not isinstance(payload, dict):
            Domoticz.Error("Stipple settings payload must be a JSON object")
            return

        self._request("PATCH", "/settings", payload)

    def navigate(self, direction):
        """
        Inject the same controls used by the Stipple web UI.

        Confirmed web UI request:
            POST /api/v1/input
            {"control": "right"}

        right = next app
        left  = previous app
        """
        control = "right" if direction == "next" else "left"
        return self._request("POST", "/input", {
            "control": control
        })

    def dismissNotifications(self):
        # The documented collection DELETE clears queued/showing notifications.
        self._request("DELETE", "/notifications")

    def setPower(self, command):
        """
        Stipple panel power:
            PATCH /api/v1/settings
            {"display":{"power":true|false}}
        """
        state = command.upper() == "ON"

        result = self._request(
            "PATCH",
            "/settings",
            {"display": {"power": state}}
        )

        if result is not None:
            Devices[UNIT_POWER].Update(
                nValue=1 if state else 0,
                sValue="On" if state else "Off"
            )

    def setBrightness(self, command, level):
        """
        Stipple stores brightness as display.brightness (0..255).
        """
        if command == "Off":
            value = 0
        else:
            try:
                percent = max(0, min(int(level), 100))
            except (TypeError, ValueError):
                percent = 100
            value = int(round(percent * 255 / 100))

        result = self._request(
            "PATCH",
            "/settings",
            {"display": {"brightness": value}}
        )

        if result is not None:
            percent = int(round(value * 100 / 255)) if value else 0
            Devices[UNIT_BRIGHTNESS].Update(
                nValue=1 if value else 0,
                sValue=str(percent)
            )

    def setAutoTransition(self, command):
        """
        Enable/disable transitions between apps:
            PATCH /api/v1/settings
            {"apps":{"transitions":true|false}}
        """
        state = command.upper() == "ON"

        result = self._request(
            "PATCH",
            "/settings",
            {"apps": {"transitions": state}}
        )

        if result is not None:
            Devices[UNIT_AUTOTRANSITION].Update(
                nValue=1 if state else 0,
                sValue="On" if state else "Off"
            )

    def setTransition(self, level):
        """
        Stipple Web UI mapping:
            PATCH /api/v1/settings
            {"apps":{"transition":"slide"}}

        Values: slide, fade, wipe, dissolve, none (Cut).
        """
        try:
            index = int(level / 10)
        except (TypeError, ValueError):
            return

        if index < 0 or index >= len(TRANSITION_VALUES):
            return

        result = self._request(
            "PATCH",
            "/settings",
            {"apps": {"transition": TRANSITION_VALUES[index]}}
        )
        if result is not None:
            Devices[UNIT_TRANSITION].Update(
                nValue=int(level),
                sValue=str(int(level))
            )

    def setOverlay(self, level):
        """
        Stipple Web UI mapping:
            PATCH /api/v1/settings
            {"display":{"overlay":"fog"}}

        Values: none, rain, snow, storm, frost, fog, stars, sparkle, confetti.
        """
        try:
            index = int(level / 10)
        except (TypeError, ValueError):
            return

        if index < 0 or index >= len(OVERLAY_VALUES):
            return

        result = self._request(
            "PATCH",
            "/settings",
            {"display": {"overlay": OVERLAY_VALUES[index]}}
        )
        if result is not None:
            Devices[UNIT_OVERLAY].Update(
                nValue=int(level),
                sValue=str(int(level))
            )

    # -------------------------------------------------------------- commands

    def pulseButtonOff(self, unit):
        try:
            Devices[unit].Update(nValue=0, sValue="Off")
        except Exception:
            pass

    def onCommand(self, Unit, Command, Level, Color):
        Domoticz.Debug(
            "onCommand Unit {}: Command='{}', Level={}, Color={}".format(
                Unit, Command, Level, Color
            )
        )

        if Unit == UNIT_POWER:
            self.setPower(Command)

        elif Unit == UNIT_NOTIFICATION:
            message = self.payloadText(Unit)
            if not message:
                Domoticz.Error("Notification payload is empty")
            else:
                self.sendNotification(self.parsePushMessage(message))
            self.pulseButtonOff(Unit)

        elif Unit == UNIT_CUSTOMAPP:
            message = self.payloadText(Unit)
            if not message:
                Domoticz.Error("Custom app payload is empty")
            else:
                self.sendCustomApp(self.parsePushMessage(message))
            self.pulseButtonOff(Unit)

        elif Unit == UNIT_SETTINGS:
            message = self.payloadText(Unit)
            if not message:
                Domoticz.Error("Settings payload is empty")
            else:
                self.sendSettings(message)
            self.pulseButtonOff(Unit)

        elif Unit == UNIT_NEXTAPP:
            self.navigate("next")
            self.pulseButtonOff(Unit)

        elif Unit == UNIT_PREVAPP:
            self.navigate("previous")
            self.pulseButtonOff(Unit)

        elif Unit == UNIT_DISMISS:
            self.dismissNotifications()
            self.pulseButtonOff(Unit)

        elif Unit == UNIT_TRANSITION:
            self.setTransition(Level)

        elif Unit == UNIT_OVERLAY:
            self.setOverlay(Level)

        elif Unit == UNIT_BRIGHTNESS:
            self.setBrightness(Command, Level)

        elif Unit == UNIT_AUTOTRANSITION:
            self.setAutoTransition(Command)

        else:
            Domoticz.Error("Unsupported Stipple unit: {}".format(Unit))

    # ------------------------------------------------------------- heartbeat

    def onHeartbeat(self):
        # Avoid hammering an offline clock.
        if self.skipTicks > 0:
            self.skipTicks -= 1
            return

        device = self._request("GET", "/device")
        if not isinstance(device, dict):
            self.failures += 1
            self.skipTicks = min(2 ** self.failures, 16) - 1
            if self.failures == 1:
                Domoticz.Log(
                    "Stipple is unreachable; backing off between retries"
                )
            return

        if self.failures:
            Domoticz.Log("Stipple is reachable again")
            self.failures = 0

        # /settings is authoritative for controls that can also be changed
        # through the Stipple web UI.
        settings = self._request("GET", "/settings")
        if not isinstance(settings, dict):
            return

        display = settings.get("display", {})
        if isinstance(display, dict):
            if "power" in display:
                state = bool(display["power"])
                Devices[UNIT_POWER].Update(
                    nValue=1 if state else 0,
                    sValue="On" if state else "Off"
                )

            if "brightness" in display:
                try:
                    raw = max(0, min(int(display["brightness"]), 255))
                    percent = int(round(raw * 100 / 255))
                    Devices[UNIT_BRIGHTNESS].Update(
                        nValue=1 if raw else 0,
                        sValue=str(percent)
                    )
                except (TypeError, ValueError):
                    pass

            if "overlay" in display:
                overlay = str(display["overlay"]).lower()
                if overlay in OVERLAY_VALUES:
                    index = OVERLAY_VALUES.index(overlay)
                    level = index * 10
                    Devices[UNIT_OVERLAY].Update(
                        nValue=level,
                        sValue=str(level)
                    )

        apps = settings.get("apps", {})
        if isinstance(apps, dict):
            if "transition" in apps:
                transition = str(apps["transition"]).lower()
                if transition in TRANSITION_VALUES:
                    index = TRANSITION_VALUES.index(transition)
                    level = index * 10
                    Devices[UNIT_TRANSITION].Update(
                        nValue=level,
                        sValue=str(level)
                    )

            if "transitions" in apps:
                state = bool(apps["transitions"])
                Devices[UNIT_AUTOTRANSITION].Update(
                    nValue=1 if state else 0,
                    sValue="On" if state else "Off"
                )


global _plugin
_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onCommand(Unit, Command, Level, Color):
    _plugin.onCommand(Unit, Command, Level, Color)


def onHeartbeat():
    _plugin.onHeartbeat()
