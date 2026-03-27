"""
Digikey Query Builder

Translates typed component specs into Digikey v4 FilterOptionsRequest bodies.
Faithfully ports all Search*1 JS nodes from the n8n workflow.

Each public function returns a list of search body dicts (one per component),
ready to be passed directly to integrations/digikey/client.keyword_search().
"""

from __future__ import annotations

# ── Shared lookup tables ──────────────────────────────────────────────────────

TOLERANCE_MAP: dict[str, str] = {
    "±0.01%": "651", "±0.05%": "696", "±0.1%": "731", "±0.25%": "848",
    "±0.5%": "976", "±1%": "1131", "±2%": "1684", "±2.5%": "1782",
    "±5%": "2503", "±10%": "1340", "±20%": "1900",
}

RESISTOR_POWER_MAP: dict[str, str] = {
    "0.03 W": "6357", "0.05 W": "7524", "0.063 W": "7854", "0.1 W": "14064",
    "0.125 W": "10879", "0.2 W": "18038", "0.25 W": "16543", "0.4 W": "25166",
    "0.5 W": "28682", "0.75 W": "33182", "1 W": "121219", "1.4 W": "53214",
    "1.5 W": "55874", "2 W": "169141", "2.4 W": "130344", "3 W": "203013",
    "3.5 W": "176624", "4 W": "228846", "5 W": "249624", "6 W": "267627",
    "7 W": "281382", "8 W": "295359", "9 W": "305591", "10 W": "74706",
    "16 W": "108856", "20 W": "143920", "25 W": "159285",
}

CAPACITOR_VOLTAGE_MAP: dict[str, int] = {
    "2.5V": 132007, "4V": 228504, "6V": 267452, "6.3V": 252155, "10V": 74515,
    "16V": 108742, "20V": 238738, "25V": 159247, "35V": 194844, "50V": 238738,
    "63V": 219853, "100V": 69629, "200V": 140848, "250V": 157291, "400V": 213650,
    "450V": 221502, "500V": 237347, "630V": 260046,
}

CAPACITOR_TEMP_COEFF_MAP: dict[str, int] = {
    "C0G": 324183, "NP0": 324183, "C0G, NP0": 324183, "X5R": 422407,
    "X7R": 422415, "X7S": 422418, "X8R": 422426, "Y5V": 423167,
    "Z5U": 423404, "X6S": 422413,
}

INDUCTOR_MANUFACTURERS = [
    {"Id": "749", "Name": "Vishay"}, {"Id": "541", "Name": "Vishay Dale"},
    {"Id": "732", "Name": "Würth Elektronik"}, {"Id": "445", "Name": "TDK Corporation"},
    {"Id": "490", "Name": "Murata Electronics"}, {"Id": "399", "Name": "KEMET"},
    {"Id": "2457", "Name": "Coilcraft"}, {"Id": "10", "Name": "Panasonic Electronic Components"},
]

RESISTOR_MANUFACTURERS = [
    {"Id": "1712", "Name": "TE Connectivity Passive Product"}, {"Id": "13", "Name": "YAGEO"},
    {"Id": "749", "Name": "Vishay"}, {"Id": "273", "Name": "Ohmite"},
    {"Id": "10", "Name": "Panasonic Electronic Components"},
    {"Id": "846", "Name": "Rohm Semiconductor"}, {"Id": "118", "Name": "Bourns Inc."},
]

CAPACITOR_MANUFACTURERS = [
    {"Id": "13", "Name": "YAGEO"}, {"Id": "749", "Name": "Vishay"},
    {"Id": "10", "Name": "Panasonic Electronic Components"},
    {"Id": "732", "Name": "Würth Elektronik"}, {"Id": "445", "Name": "TDK Corporation"},
    {"Id": "490", "Name": "Murata Electronics"}, {"Id": "478", "Name": "KYOCERA AVX"},
    {"Id": "399", "Name": "KEMET"},
]

FUSE_MANUFACTURERS = [
    {"Id": "507", "Name": "Bel Fuse Inc."}, {"Id": "749", "Name": "Vishay"},
    {"Id": "10", "Name": "Panasonic Electronic Components"},
    {"Id": "18", "Name": "Littelfuse Inc."}, {"Id": "732", "Name": "Würth Elektronik"},
    {"Id": "118", "Name": "Bourns Inc."},
]

TVS_MANUFACTURERS = [
    {"Id": "749", "Name": "Vishay"}, {"Id": "732", "Name": "Würth Elektronik"},
    {"Id": "18", "Name": "Littelfuse Inc."}, {"Id": "31", "Name": "Diodes Incorporated"},
    {"Id": "488", "Name": "onsemi"}, {"Id": "497", "Name": "STMicroelectronics"},
]

DIODE_MANUFACTURERS = [
    {"Id": "749", "Name": "Vishay"}, {"Id": "18", "Name": "Littelfuse Inc."},
    {"Id": "732", "Name": "Würth Elektronik"}, {"Id": "448", "Name": "Infineon Technologies"},
    {"Id": "31", "Name": "Diodes Incorporated"}, {"Id": "488", "Name": "onsemi"},
    {"Id": "846", "Name": "Rohm Semiconductor"}, {"Id": "1727", "Name": "Nexperia USA Inc."},
    {"Id": "497", "Name": "STMicroelectronics"},
]

MOSFET_MANUFACTURERS = [
    {"Id": "749", "Name": "Vishay"}, {"Id": "296", "Name": "Texas Instruments"},
    {"Id": "846", "Name": "Rohm Semiconductor"}, {"Id": "488", "Name": "onsemi"},
    {"Id": "1727", "Name": "Nexperia USA Inc."}, {"Id": "448", "Name": "Infineon Technologies"},
    {"Id": "31", "Name": "Diodes Incorporated"},
]

TRANSFORMER_MANUFACTURERS = [
    {"Id": "732", "Name": "Würth Elektronik"}, {"Id": "749", "Name": "Vishay"},
    {"Id": "445", "Name": "TDK Corporation"}, {"Id": "118", "Name": "Bourns Inc."},
    {"Id": "490", "Name": "Murata Electronics"}, {"Id": "2457", "Name": "Coilcraft"},
]

CONNECTOR_MANUFACTURERS = [
    {"Id": "952", "Name": "Harwin Inc."}, {"Id": "732", "Name": "Würth Elektronik"},
    {"Id": "17", "Name": "TE Connectivity AMP Connectors"}, {"Id": "612", "Name": "Samtec Inc."},
    {"Id": "23", "Name": "Molex"}, {"Id": "609", "Name": "Amphenol ICC (FCI)"},
]

CONNECTOR_POSITION_MAP: dict[int, int] = {
    1: 39665, 2: 121326, 3: 169295, 4: 203167, 5: 229001, 6: 249730,
    7: 267825, 8: 281410, 9: 295538, 10: 63986, 12: 80383, 15: 97513,
    20: 137796, 24: 151929, 25: 155383,
}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _base_search(
    category_id: str,
    manufacturers: list[dict],
    parameter_filters: list[dict],
    keywords: str = "",
    limit: int = 30,
) -> dict:
    """Build the standard Digikey v4 search request body."""
    return {
        "Keywords": keywords,
        "Limit": limit,
        "Offset": 0,
        "FilterOptionsRequest": {
            "CategoryFilter": [{"Id": category_id}],
            "ManufacturerFilter": manufacturers,
            "ParameterFilterRequest": {
                "CategoryFilter": {"Id": category_id},
                "ParameterFilters": [f for f in parameter_filters if f],
            },
            "SearchOptions": [],
        },
        "SortOptions": {"Field": "QuantityAvailable", "SortOrder": "Descending"},
    }


def _normalize_voltage(v: str | None) -> str | None:
    if not v:
        return None
    return v.upper().replace(" ", "").replace("VDC", "V").strip()


def _parse_float(s: str | None) -> float | None:
    if not s:
        return None
    try:
        import re
        m = re.search(r"[\d.]+", str(s))
        return float(m.group()) if m else None
    except ValueError:
        return None


def _extract_power_id(raw_power: str | None) -> str | None:
    if not raw_power:
        return None
    for p in raw_power.replace(";", ",").split(","):
        p = p.strip()
        if p in RESISTOR_POWER_MAP:
            return RESISTOR_POWER_MAP[p]
    for p in raw_power.replace(";", ",").split(","):
        p = p.strip()
        for key, val in RESISTOR_POWER_MAP.items():
            if p in key or key in p:
                return val
    return None


def _generate_current_ratings(value_text: str | None) -> list[str]:
    if not value_text:
        return []
    val = _parse_float(value_text)
    if val is None:
        return []
    results = [val]
    if val < 100:
        max_limit = (int(val / 10) + 1) * 10
        i = round(val * 10 + 1) / 10
        while i <= max_limit:
            results.append(round(i, 1))
            i = round(i + 0.1, 1)
    else:
        i = int(val) + 1
        while i <= 200:
            results.append(i)
            i += 1
    return [f"{r} A" for r in results]


def _get_closest_position_id(n: str | int) -> dict:
    num = int(str(n)) if n else 2
    for k in sorted(CONNECTOR_POSITION_MAP.keys()):
        if k >= num:
            return {"Id": str(CONNECTOR_POSITION_MAP[k]), "ValueText": str(k)}
    last = max(CONNECTOR_POSITION_MAP.keys())
    return {"Id": str(CONNECTOR_POSITION_MAP[last]), "ValueText": str(last)}


# ── Public query builders ─────────────────────────────────────────────────────

def build_resistor_searches(resistors: list[dict]) -> list[dict]:
    searches = []
    for r in resistors:
        tolerance_id = TOLERANCE_MAP.get(r.get("tolerance", ""), None)
        power_id = _extract_power_id(r.get("power_rating"))

        filters = [
            {
                "ParameterId": 2085, "ParameterText": "Resistance",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": r.get("resistance"), "ValueText": r.get("resistance")}],
            } if r.get("resistance") else None,
            {
                "ParameterId": 3, "ParameterText": "Tolerance",
                "ParameterType": "String",
                "FilterValues": [{"Id": tolerance_id, "ValueText": r.get("tolerance")}],
            } if tolerance_id else None,
            {
                "ParameterId": 2, "ParameterText": "Power (Watts)",
                "ParameterType": "String",
                "FilterValues": [{"Id": power_id, "ValueText": r.get("power_rating")}],
            } if power_id else None,
        ]
        searches.append(_base_search("52", RESISTOR_MANUFACTURERS, [f for f in filters if f]))
    return searches


def build_shunt_searches(shunts: list[dict]) -> list[dict]:
    # Same logic as resistors — same category ID
    return build_resistor_searches(shunts)


def build_capacitor_searches(capacitors: list[dict]) -> list[dict]:
    searches = []
    for c in capacitors:
        cap_val = (c.get("capacitance") or "").replace("uF", "µF").replace("UF", "µF").strip()
        tolerance_id = TOLERANCE_MAP.get(c.get("tolerance", ""), None)
        norm_v = _normalize_voltage(c.get("voltage_rating"))
        voltage_id = str(CAPACITOR_VOLTAGE_MAP.get(norm_v, "")) if norm_v else None

        # Temperature coefficient from type field
        temp_coeff = None
        for key, val in CAPACITOR_TEMP_COEFF_MAP.items():
            if key.upper() in (c.get("type") or "").upper():
                temp_coeff = {"Id": str(val), "ValueText": key}
                break

        filters = [
            {
                "ParameterId": "2049", "ParameterText": "Capacitance",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": cap_val, "ValueText": cap_val}],
            } if cap_val else None,
            {
                "ParameterId": "3", "ParameterText": "Tolerance",
                "ParameterType": "String",
                "FilterValues": [{"Id": tolerance_id, "ValueText": c.get("tolerance")}],
            } if tolerance_id else None,
            {
                "ParameterId": "14", "ParameterText": "Voltage - Rated",
                "ParameterType": "String",
                "FilterValues": [{"Id": voltage_id, "ValueText": norm_v}],
            } if voltage_id else None,
            {
                "ParameterId": "17", "ParameterText": "Temperature Coefficient",
                "ParameterType": "String",
                "FilterValues": [temp_coeff],
            } if temp_coeff else None,
        ]
        searches.append(_base_search("60", CAPACITOR_MANUFACTURERS, [f for f in filters if f]))
    return searches


def build_electrolytic_searches(capacitors: list[dict]) -> list[dict]:
    searches = []
    for c in capacitors:
        cap_val = (c.get("capacitance") or "").strip()
        tolerance_id = TOLERANCE_MAP.get(c.get("tolerance", ""), None)
        voltage_val = (c.get("voltage_rating") or "").strip()

        filters = [
            {
                "ParameterId": 2049, "ParameterText": "Capacitance",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": cap_val, "ValueText": cap_val}],
            } if cap_val else None,
            {
                "ParameterId": 3, "ParameterText": "Tolerance",
                "ParameterType": "String",
                "FilterValues": [{"Id": tolerance_id, "ValueText": c.get("tolerance")}],
            } if tolerance_id else None,
            {
                "ParameterId": 2079, "ParameterText": "Voltage - Rated",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": voltage_val, "ValueText": voltage_val}],
            } if voltage_val else None,
        ]
        searches.append(_base_search("58", CAPACITOR_MANUFACTURERS, [f for f in filters if f]))
    return searches


def build_fuse_searches(fuses: list[dict]) -> list[dict]:
    """Fuses use fixed current/voltage filters as in the original workflow."""
    searches = []
    for _ in fuses:
        filters = [
            {
                "ParameterId": 2088, "ParameterText": "Current Rating (Amps)",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": "1 A", "ValueText": "1 A"}],
            },
            {
                "ParameterId": 2144, "ParameterText": "Voltage Rating - DC",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": "32 V", "ValueText": "32 V"}],
            },
        ]
        searches.append(_base_search("139", FUSE_MANUFACTURERS, filters))
    return searches


def build_inductor_searches(inductors: list[dict]) -> list[dict]:
    searches = []
    for ind in inductors:
        inductance = ind.get("inductance")
        tolerance_id = TOLERANCE_MAP.get(ind.get("tolerance") or "±20%", "1900")
        current_vals = _generate_current_ratings(ind.get("current_rating"))

        filters = [
            {
                "ParameterId": 2087, "ParameterText": "Inductance",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": inductance, "ValueText": inductance}],
            } if inductance else None,
            {
                "ParameterId": 2088, "ParameterText": "Current Rating (Amps)",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": v, "ValueText": v} for v in current_vals],
            } if current_vals else None,
            {
                "ParameterId": 3, "ParameterText": "Tolerance",
                "ParameterType": "String",
                "FilterValues": [{"Id": tolerance_id, "ValueText": ind.get("tolerance") or "±20%"}],
            },
        ]
        searches.append(_base_search("71", INDUCTOR_MANUFACTURERS, [f for f in filters if f]))
    return searches


def build_tvs_searches(tvs_diodes: list[dict]) -> list[dict]:
    searches = []
    for tvs in tvs_diodes:
        polarity = (tvs.get("polarity") or "").lower()
        filters: list[dict] = []

        if polarity == "unidirectional":
            filters.append({
                "ParameterId": 1729, "ParameterText": "Unidirectional Channels",
                "ParameterType": "Double",
                "FilterValues": [{"Id": "1", "ValueText": "1"}],
            })
        elif polarity == "bidirectional":
            filters.append({
                "ParameterId": 1730, "ParameterText": "Bidirectional Channels",
                "ParameterType": "Double",
                "FilterValues": [{"Id": "1", "ValueText": "1"}],
            })

        searches.append(_base_search("144", TVS_MANUFACTURERS, filters))
    return searches


def build_diode_searches(diodes: list[dict]) -> list[dict]:
    searches = []
    for d in diodes:
        mounting_filter = {
            "ParameterId": 69, "ParameterText": "Mounting Type",
            "ParameterType": "String",
            "FilterValues": [{"Id": "409393", "ValueText": "Surface Mount"}],
        }

        filters = [mounting_filter]

        reverse_v = d.get("reverse_voltage")
        if reverse_v:
            v_num = _parse_float(reverse_v)
            if v_num:
                voltage_values = [
                    {"Id": f"{int(v_num + i * 10)} V", "ValueText": f"{int(v_num + i * 10)} V"}
                    for i in range(20)
                ]
                filters.append({
                    "ParameterId": 2071, "ParameterText": "Voltage - DC Reverse (Vr) (Max)",
                    "ParameterType": "UnitOfMeasure",
                    "FilterValues": voltage_values,
                })

        # Schottky filter if diode_type mentions it
        diode_type = (d.get("diode_type") or "").lower()
        if any(t in diode_type for t in ("schottky", "fast", "ultrafast")):
            filters.append({
                "ParameterId": 570, "ParameterText": "Technology",
                "ParameterType": "String",
                "FilterValues": [{"Id": "400378", "ValueText": "Schottky"}],
            })

        searches.append(
            _base_search("280", DIODE_MANUFACTURERS, filters, keywords=d.get("partNumber") or "")
        )
    return searches


def build_zener_searches(zeners: list[dict]) -> list[dict]:
    searches = []
    for z in zeners:
        mounting_filter = {
            "ParameterId": 69, "ParameterText": "Mounting Type",
            "ParameterType": "String",
            "FilterValues": [{"Id": "409393", "ValueText": "Surface Mount"}],
        }
        filters = [mounting_filter]

        zener_v = z.get("zener_voltage")
        if zener_v:
            filters.append({
                "ParameterId": 920, "ParameterText": "Voltage - Zener (Nom) (Vz)",
                "ParameterType": "UnitOfMeasure",
                "FilterValues": [{"Id": zener_v, "ValueText": zener_v}],
            })

        searches.append(
            _base_search("287", DIODE_MANUFACTURERS, filters, keywords=z.get("partNumber") or "")
        )
    return searches


def build_mosfet_searches(mosfets: list[dict]) -> list[dict]:
    searches = []
    for m in mosfets:
        filters = []

        vds = m.get("vds_voltage")
        if vds:
            v = _parse_float(vds)
            if v is not None:
                step = 1 if v < 100 else (5 if v < 1000 else 50)
                vds_values = [
                    {"Id": f"{int(v + i * step)} V", "ValueText": f"{int(v + i * step)} V"}
                    for i in range(20)
                ]
                filters.append({
                    "ParameterId": 2068, "ParameterText": "Drain to Source Voltage (Vdss)",
                    "ParameterType": "UnitOfMeasure",
                    "FilterValues": vds_values,
                })

        searches.append(
            _base_search("278", MOSFET_MANUFACTURERS, filters, keywords=m.get("partNumber") or "")
        )
    return searches


def build_transformer_searches(transformers: list[dict]) -> list[dict]:
    searches = []
    for t in transformers:
        inductance = t.get("primary_magnetizing_inductance")
        if not inductance:
            continue

        filters = [
            {
                "ParameterId": 19, "ParameterText": "Inductance",
                "ParameterType": "String",
                "FilterValues": [{"Id": inductance, "ValueText": inductance}],
            }
        ]

        searches.append(
            _base_search("166", TRANSFORMER_MANUFACTURERS, filters, keywords=t.get("partNumber") or "")
        )
    return searches


def build_connector_searches(connectors: list[dict]) -> list[dict]:
    searches = []
    for c in connectors:
        position = _get_closest_position_id(c.get("number_of_contacts") or 2)
        mounting = (c.get("mounting_type") or "").lower()

        filters = [
            {
                "ParameterId": 88, "ParameterText": "Number of Positions",
                "ParameterType": "String",
                "FilterValues": [position],
            }
        ]

        if "through" in mounting:
            filters.append({
                "ParameterId": 69, "ParameterText": "Mounting Type",
                "ParameterType": "String",
                "FilterValues": [{"Id": "411897", "ValueText": "Through Hole"}],
            })
        elif "surface" in mounting:
            filters.append({
                "ParameterId": 69, "ParameterText": "Mounting Type",
                "ParameterType": "String",
                "FilterValues": [{"Id": "409393", "ValueText": "Surface Mount"}],
            })

        searches.append(_base_search("314", CONNECTOR_MANUFACTURERS, filters))
    return searches
