"""Kraj płatności kartą — do grupowania zagranicznych transakcji w kolejce „Do przejrzenia”.

Millennium nie podaje kraju w osobnym polu; jest w opisie:
- płatność kartą na rachunku (CSV i API): `SPRZEDAWCA … MIEJSCOWOŚĆ KOD RRRR-MM-DD` — kod
  bywa sklejony z nazwą miejscowości (`…XyzKOD RRRR-MM-DD`);
- konto karty kredytowej (API): kod jako ostatnie słowo (`… XYZ LUX`) albo brak kodu.

Kod sprawdzany z listą ISO 3166-1 alfa-3, więc końcówki nazw firm („SRL”, „SPA”) i domen
(„.COM”) nie udają kraju. Bez kodu, ale z walutą oryginalną inną niż PLN → „Zagranica (EUR)”.
API obcina długie opisy (~60 znaków) razem z kodem — taka płatność liczy się jak krajowa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from budget.kinds import Kind

HOME = "POL"
_CARD_KINDS = frozenset({Kind.CARD.value, Kind.CARD_REFUND.value})
# Kod przed datą: wielkie litery w oryginale (sklejenie z miastem pisanym małymi dopuszczalne)
_BEFORE_DATE_RE = re.compile(r"([A-Z]{3})\s*\d{4}-\d{2}-\d{2}\W*$")
# Kod jako ostatnie słowo (po spacji, nie po kropce domeny)
_LAST_WORD_RE = re.compile(r"(?:^|\s)([A-Z]{3})\W*$")

# ISO 3166-1 alfa-3 → nazwa po polsku (bez kraju domowego — ten nigdy nie jest grupą)
NAMES: dict[str, str] = {
    "ABW": "Aruba", "AFG": "Afganistan", "AGO": "Angola", "AIA": "Anguilla",
    "ALA": "Wyspy Alandzkie", "ALB": "Albania", "AND": "Andora",
    "ARE": "Zjednoczone Emiraty Arabskie", "ARG": "Argentyna", "ARM": "Armenia",
    "ASM": "Samoa Amerykańskie", "ATA": "Antarktyka", "ATF": "Francuskie Terytoria Południowe",
    "ATG": "Antigua i Barbuda", "AUS": "Australia", "AUT": "Austria", "AZE": "Azerbejdżan",
    "BDI": "Burundi", "BEL": "Belgia", "BEN": "Benin", "BES": "Bonaire, Sint Eustatius i Saba",
    "BFA": "Burkina Faso", "BGD": "Bangladesz", "BGR": "Bułgaria", "BHR": "Bahrajn",
    "BHS": "Bahamy", "BIH": "Bośnia i Hercegowina", "BLM": "Saint-Barthélemy",
    "BLR": "Białoruś", "BLZ": "Belize", "BMU": "Bermudy", "BOL": "Boliwia", "BRA": "Brazylia",
    "BRB": "Barbados", "BRN": "Brunei", "BTN": "Bhutan", "BVT": "Wyspa Bouveta",
    "BWA": "Botswana", "CAF": "Republika Środkowoafrykańska", "CAN": "Kanada",
    "CCK": "Wyspy Kokosowe", "CHE": "Szwajcaria", "CHL": "Chile", "CHN": "Chiny",
    "CIV": "Wybrzeże Kości Słoniowej", "CMR": "Kamerun", "COD": "Demokratyczna Republika Konga",
    "COG": "Kongo", "COK": "Wyspy Cooka", "COL": "Kolumbia", "COM": "Komory",
    "CPV": "Republika Zielonego Przylądka", "CRI": "Kostaryka", "CUB": "Kuba",
    "CUW": "Curaçao", "CXR": "Wyspa Bożego Narodzenia", "CYM": "Kajmany", "CYP": "Cypr",
    "CZE": "Czechy", "DEU": "Niemcy", "DJI": "Dżibuti", "DMA": "Dominika", "DNK": "Dania",
    "DOM": "Dominikana", "DZA": "Algieria", "ECU": "Ekwador", "EGY": "Egipt",
    "ERI": "Erytrea", "ESH": "Sahara Zachodnia", "ESP": "Hiszpania", "EST": "Estonia",
    "ETH": "Etiopia", "FIN": "Finlandia", "FJI": "Fidżi", "FLK": "Falklandy",
    "FRA": "Francja", "FRO": "Wyspy Owcze", "FSM": "Mikronezja", "GAB": "Gabon",
    "GBR": "Wielka Brytania", "GEO": "Gruzja", "GGY": "Guernsey", "GHA": "Ghana",
    "GIB": "Gibraltar", "GIN": "Gwinea", "GLP": "Gwadelupa", "GMB": "Gambia",
    "GNB": "Gwinea Bissau", "GNQ": "Gwinea Równikowa", "GRC": "Grecja", "GRD": "Grenada",
    "GRL": "Grenlandia", "GTM": "Gwatemala", "GUF": "Gujana (Francja)", "GUM": "Guam",
    "GUY": "Gujana", "HKG": "Hongkong", "HMD": "Wyspy Heard i McDonalda", "HND": "Honduras",
    "HRV": "Chorwacja", "HTI": "Haiti", "HUN": "Węgry", "IDN": "Indonezja",
    "IMN": "Wyspa Man", "IND": "Indie", "IOT": "Brytyjskie Terytorium Oceanu Indyjskiego",
    "IRL": "Irlandia", "IRN": "Iran", "IRQ": "Irak", "ISL": "Islandia", "ISR": "Izrael",
    "ITA": "Włochy", "JAM": "Jamajka", "JEY": "Jersey", "JOR": "Jordania", "JPN": "Japonia",
    "KAZ": "Kazachstan", "KEN": "Kenia", "KGZ": "Kirgistan", "KHM": "Kambodża",
    "KIR": "Kiribati", "KNA": "Saint Kitts i Nevis", "KOR": "Korea Południowa",
    "KWT": "Kuwejt", "LAO": "Laos", "LBN": "Liban", "LBR": "Liberia", "LBY": "Libia",
    "LCA": "Saint Lucia", "LIE": "Liechtenstein", "LKA": "Sri Lanka", "LSO": "Lesotho",
    "LTU": "Litwa", "LUX": "Luksemburg", "LVA": "Łotwa", "MAC": "Makau",
    "MAF": "Saint-Martin", "MAR": "Maroko", "MCO": "Monako", "MDA": "Mołdawia",
    "MDG": "Madagaskar", "MDV": "Malediwy", "MEX": "Meksyk", "MHL": "Wyspy Marshalla",
    "MKD": "Macedonia Północna", "MLI": "Mali", "MLT": "Malta", "MMR": "Mjanma",
    "MNE": "Czarnogóra", "MNG": "Mongolia", "MNP": "Mariany Północne", "MOZ": "Mozambik",
    "MRT": "Mauretania", "MSR": "Montserrat", "MTQ": "Martynika", "MUS": "Mauritius",
    "MWI": "Malawi", "MYS": "Malezja", "MYT": "Majotta", "NAM": "Namibia",
    "NCL": "Nowa Kaledonia", "NER": "Niger", "NFK": "Norfolk", "NGA": "Nigeria",
    "NIC": "Nikaragua", "NIU": "Niue", "NLD": "Holandia", "NOR": "Norwegia", "NPL": "Nepal",
    "NRU": "Nauru", "NZL": "Nowa Zelandia", "OMN": "Oman", "PAK": "Pakistan",
    "PAN": "Panama", "PCN": "Pitcairn", "PER": "Peru", "PHL": "Filipiny", "PLW": "Palau",
    "PNG": "Papua-Nowa Gwinea", "PRI": "Portoryko", "PRK": "Korea Północna",
    "PRT": "Portugalia", "PRY": "Paragwaj", "PSE": "Palestyna",
    "PYF": "Polinezja (Francja)", "QAT": "Katar", "REU": "Reunion", "ROU": "Rumunia",
    "RUS": "Rosja", "RWA": "Rwanda", "SAU": "Arabia Saudyjska", "SDN": "Sudan",
    "SEN": "Senegal", "SGP": "Singapur", "SGS": "Georgia Południowa i Sandwich Południowy",
    "SHN": "Wyspa Świętej Heleny", "SJM": "Svalbard i Jan Mayen", "SLB": "Wyspy Salomona",
    "SLE": "Sierra Leone", "SLV": "Salwador", "SMR": "San Marino", "SOM": "Somalia",
    "SPM": "Saint-Pierre i Miquelon", "SRB": "Serbia", "SSD": "Sudan Południowy",
    "STP": "Wyspy Świętego Tomasza i Książęca", "SUR": "Surinam", "SVK": "Słowacja",
    "SVN": "Słowenia", "SWE": "Szwecja", "SWZ": "Eswatini", "SXM": "Sint Maarten",
    "SYC": "Seszele", "SYR": "Syria", "TCA": "Turks i Caicos", "TCD": "Czad", "TGO": "Togo",
    "THA": "Tajlandia", "TJK": "Tadżykistan", "TKL": "Tokelau", "TKM": "Turkmenistan",
    "TLS": "Timor Wschodni", "TON": "Tonga", "TTO": "Trynidad i Tobago", "TUN": "Tunezja",
    "TUR": "Turcja", "TUV": "Tuvalu", "TWN": "Tajwan", "TZA": "Tanzania", "UGA": "Uganda",
    "UKR": "Ukraina", "UMI": "Dalekie Wyspy Mniejsze Stanów Zjednoczonych", "URY": "Urugwaj",
    "USA": "Stany Zjednoczone", "UZB": "Uzbekistan", "VAT": "Watykan",
    "VCT": "Saint Vincent i Grenadyny", "VEN": "Wenezuela",
    "VGB": "Brytyjskie Wyspy Dziewicze", "VIR": "Wyspy Dziewicze Stanów Zjednoczonych",
    "VNM": "Wietnam", "VUT": "Vanuatu", "WLF": "Wallis i Futuna", "WSM": "Samoa",
    "YEM": "Jemen", "ZAF": "Republika Południowej Afryki", "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}  # fmt: skip


@dataclass(frozen=True)
class Origin:
    """Zagraniczne pochodzenie płatności: kod kraju albo (bez kodu) waluta oryginalna."""

    key: str  # „CHE” albo „waluta:EUR”
    label: str  # „Szwajcaria” / „Zagranica (EUR)”


def code_from_description(description: str | None) -> str | None:
    """Kod kraju z opisu karty (`HOME` też), jeśli jest i figuruje w ISO 3166-1 alfa-3."""
    text = (description or "").rstrip()
    for pattern in (_BEFORE_DATE_RE, _LAST_WORD_RE):
        m = pattern.search(text)
        if m and (m.group(1) == HOME or m.group(1) in NAMES):
            return m.group(1)
    return None


def card_origin(kind: str, description: str | None, orig_currency: str | None) -> Origin | None:
    """Kraj zagranicznej płatności kartą; `None` — krajowa, nieznana albo nie karta."""
    if kind not in _CARD_KINDS:
        return None
    code = code_from_description(description)
    if code == HOME:
        return None
    if code is not None:
        return Origin(code, NAMES[code])
    currency = (orig_currency or "").strip().upper()
    if currency and currency != "PLN":
        return Origin(f"waluta:{currency}", f"Zagranica ({currency})")
    return None
