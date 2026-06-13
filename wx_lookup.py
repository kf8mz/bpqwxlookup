#!/usr/bin/env python3
"""
wx_lookup.py  -  LinBPQ weather lookup application
Runs as an inetd service; stdin/stdout are the user's packet session.

Source  : api.weather.gov (NOAA/NWS) - FREE, no API key required
Coverage: US zip codes only

Shows: Current conditions, 7-period forecast, active alerts.

Add to bpq32.cfg:
  APP 5,WX,ATT 5  127.0.0.1 63013 TELNET LOOP,,WX,255 CONV

Add to /etc/services:
  wx  63013/tcp

Add to /etc/inetd.conf:
  wx  stream  tcp  nowait  pi  /home/pi/linbpq/scripts/wx_lookup.py  wx_lookup.py
"""

import sys
import requests

TIMEOUT = 10
HEADERS = {"User-Agent": "LinBPQ-WX/1.0 (amateur radio node; contact your-call@example.com)"}

# NWS requires a User-Agent header - update the email above with your callsign/email


def flush(text: str):
    sys.stdout.write(text)
    sys.stdout.flush()


def hr():
    return "-" * 40 + "\r\n"


def zip_to_latlon(zipcode: str):
    """Convert US zip code to lat/lon using the NWS points API."""
    # NWS doesn't do zip lookup directly; use geocode via nominatim (OSM) - no key needed
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"postalcode": zipcode, "country": "US", "format": "json", "limit": 1},
            headers={"User-Agent": "LinBPQ-WX/1.0"},
            timeout=TIMEOUT,
        )
        data = r.json()
        if not data:
            return None, None, None
        lat  = float(data[0]["lat"])
        lon  = float(data[0]["lon"])
        name = data[0].get("display_name", "").split(",")[0]
        return lat, lon, name
    except Exception:
        return None, None, None


def get_nws_endpoints(lat: float, lon: float):
    """Get NWS grid endpoints for a lat/lon."""
    try:
        r = requests.get(
            f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}",
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        data = r.json()
        props = data.get("properties", {})
        forecast_url  = props.get("forecast")
        station_url   = props.get("observationStations")
        alerts_zone   = props.get("county", "")        # used for alerts
        city          = props.get("relativeLocation", {}).get("properties", {}).get("city", "")
        state         = props.get("relativeLocation", {}).get("properties", {}).get("state", "")
        return forecast_url, station_url, alerts_zone, city, state
    except Exception:
        return None, None, None, "", ""


def get_current_conditions(station_url: str) -> str:
    """Get current conditions from the nearest observation station."""
    try:
        # Get list of stations, pick first
        r = requests.get(station_url, headers=HEADERS, timeout=TIMEOUT)
        stations = r.json().get("features", [])
        if not stations:
            return "  Current conditions unavailable.\r\n"
        station_id = stations[0]["properties"]["stationIdentifier"]
        station_name = stations[0]["properties"]["name"]

        # Get latest observation
        r2 = requests.get(
            f"https://api.weather.gov/stations/{station_id}/observations/latest",
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        obs = r2.json().get("properties", {})

        def val(key, unit="", divisor=1, decimals=1):
            v = obs.get(key, {})
            if isinstance(v, dict):
                v = v.get("value")
            if v is None:
                return "N/A"
            v = round(v / divisor, decimals)
            return f"{v}{unit}"

        # Temperature: C to F
        temp_c = obs.get("temperature", {}).get("value")
        temp_str = f"{temp_c * 9/5 + 32:.1f}F / {temp_c:.1f}C" if temp_c is not None else "N/A"

        dewpoint_c = obs.get("dewpoint", {}).get("value")
        dew_str = f"{dewpoint_c * 9/5 + 32:.1f}F / {dewpoint_c:.1f}C" if dewpoint_c is not None else "N/A"

        wind_speed_ms = obs.get("windSpeed", {}).get("value")
        wind_mph = f"{wind_speed_ms * 2.237:.0f} mph" if wind_speed_ms is not None else "N/A"

        wind_dir = obs.get("windDirection", {}).get("value")
        wind_dir_str = f"{wind_dir:.0f} deg" if wind_dir is not None else "N/A"

        humidity = obs.get("relativeHumidity", {}).get("value")
        humidity_str = f"{humidity:.0f}%" if humidity is not None else "N/A"

        baro_pa = obs.get("barometricPressure", {}).get("value")
        baro_str = f"{baro_pa / 3386.39:.2f} inHg" if baro_pa is not None else "N/A"

        vis_m = obs.get("visibility", {}).get("value")
        vis_str = f"{vis_m / 1609.34:.1f} mi" if vis_m is not None else "N/A"

        description = obs.get("textDescription", "N/A")
        timestamp   = obs.get("timestamp", "N/A")[:16].replace("T", " ")

        lines = [
            f"  Station   : {station_name} ({station_id})\r\n",
            f"  Observed  : {timestamp} UTC\r\n",
            f"  Sky       : {description}\r\n",
            f"  Temp      : {temp_str}\r\n",
            f"  Dewpoint  : {dew_str}\r\n",
            f"  Humidity  : {humidity_str}\r\n",
            f"  Wind      : {wind_dir_str} at {wind_mph}\r\n",
            f"  Pressure  : {baro_str}\r\n",
            f"  Visibility: {vis_str}\r\n",
        ]
        return "".join(lines)
    except Exception as e:
        return f"  Current conditions error: {e}\r\n"


def get_forecast(forecast_url: str) -> str:
    """Get 7-period NWS text forecast."""
    try:
        r = requests.get(forecast_url, headers=HEADERS, timeout=TIMEOUT)
        periods = r.json().get("properties", {}).get("periods", [])
        if not periods:
            return "  Forecast unavailable.\r\n"
        lines = []
        for p in periods[:7]:
            name     = p.get("name", "")
            temp     = p.get("temperature", "?")
            temp_u   = p.get("temperatureUnit", "F")
            wind_s   = p.get("windSpeed", "")
            wind_d   = p.get("windDirection", "")
            short    = p.get("shortForecast", "")
            precip   = p.get("probabilityOfPrecipitation", {})
            precip_v = precip.get("value") if isinstance(precip, dict) else None
            precip_str = f"  PoP:{precip_v}%" if precip_v is not None else ""
            lines.append(
                f"  {name:<17}: {temp}{temp_u}  {wind_d} {wind_s:<12} {short}{precip_str}\r\n"
            )
        return "".join(lines)
    except Exception as e:
        return f"  Forecast error: {e}\r\n"


def get_alerts(lat: float, lon: float) -> str:
    """Get active NWS alerts for the area."""
    try:
        r = requests.get(
            f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}",
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        features = r.json().get("features", [])
        if not features:
            return "  No active alerts.\r\n"
        lines = []
        for f in features[:5]:
            props = f.get("properties", {})
            event    = props.get("event", "Unknown")
            headline = props.get("headline", "")
            severity = props.get("severity", "")
            expires  = props.get("expires", "")[:16].replace("T", " ") if props.get("expires") else ""
            lines.append(f"  *** {event} ({severity}) ***\r\n")
            if headline:
                # Word-wrap headline to 38 chars
                words = headline.split()
                line = "  "
                for w in words:
                    if len(line) + len(w) + 1 > 38:
                        lines.append(line.rstrip() + "\r\n")
                        line = "  " + w + " "
                    else:
                        line += w + " "
                if line.strip():
                    lines.append(line.rstrip() + "\r\n")
            if expires:
                lines.append(f"  Expires: {expires} UTC\r\n")
            lines.append("\r\n")
        return "".join(lines)
    except Exception as e:
        return f"  Alerts error: {e}\r\n"


def do_wx(zipcode: str) -> None:
    flush(f"Looking up zip code {zipcode}...\r\n")

    lat, lon, place = zip_to_latlon(zipcode)
    if lat is None:
        flush(f"  Could not find zip code {zipcode}.\r\n")
        return

    forecast_url, station_url, alerts_zone, city, state = get_nws_endpoints(lat, lon)
    location = f"{city}, {state}" if city else place

    flush(hr())
    flush(f"  Weather for {zipcode}  {location}\r\n")
    flush(f"  Lat/Lon: {lat:.4f}, {lon:.4f}\r\n")
    flush(hr())

    flush("  CURRENT CONDITIONS\r\n")
    flush(hr())
    if station_url:
        flush(get_current_conditions(station_url))
    else:
        flush("  Observation stations unavailable.\r\n")
    flush(hr())

    flush("  7-PERIOD FORECAST\r\n")
    flush(hr())
    if forecast_url:
        flush(get_forecast(forecast_url))
    else:
        flush("  Forecast unavailable.\r\n")
    flush(hr())

    flush("  ACTIVE ALERTS\r\n")
    flush(hr())
    flush(get_alerts(lat, lon))
    flush(hr())


def main():
    try:
        user_call = sys.stdin.readline().strip()
    except Exception:
        user_call = "UNKNOWN"

    flush(f"\r\nNWS Weather Lookup  -  connected as {user_call}\r\n")
    flush("Enter a US zip code, or Q to quit.\r\n")

    quit_cmds = {"q", "b", "bye", "quit", "exit"}

    while True:
        flush("Zip Code> ")
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        if not line:
            break

        query = line.strip()
        if not query:
            continue

        if query.lower() in quit_cmds:
            flush("73 de WX!  Bye.\r\n")
            break

        if not (query.isdigit() and len(query) == 5):
            flush("  Please enter a 5-digit US zip code.\r\n")
            continue

        do_wx(query)
        flush("\r\n")


if __name__ == "__main__":
    main()
