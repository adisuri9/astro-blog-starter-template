"""Take-home pay, cost of living and savings estimates for comparing offers and cities.

Planning estimates on 2026 rules, simplified: employment income only (RSUs taxed as salary), standard
deductions, no investment income, credits or local levies beyond those listed. Verify decision-critical
numbers with a tax adviser.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .. import config

Brackets = list[tuple[float | None, float]]  # (upper bound of the band, marginal rate); None = no ceiling


def progressive(amount: float, brackets: Brackets) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in brackets:
        if amount <= lower:
            break
        top = amount if upper is None else min(amount, upper)
        tax += (top - lower) * rate
        if upper is None:
            break
        lower = upper
    return tax


# --- United States -------------------------------------------------------------------------------

US_FEDERAL = {  # 2026: (standard deduction, brackets)
    "mfj": (32_200, [(24_800, 0.10), (100_800, 0.12), (211_400, 0.22), (403_550, 0.24), (512_450, 0.32), (768_700, 0.35), (None, 0.37)]),
    "single": (16_100, [(12_400, 0.10), (50_400, 0.12), (105_700, 0.22), (201_775, 0.24), (256_225, 0.32), (640_600, 0.35), (None, 0.37)]),
}
US_SS_WAGE_BASE = 184_500

US_STATES = {
    "CA": {
        "deduction": {"mfj": 11_412, "single": 5_706},
        "brackets": {
            "mfj": [(22_108, 0.01), (52_420, 0.02), (82_738, 0.04), (114_860, 0.06), (145_172, 0.08), (741_516, 0.093), (889_808, 0.103), (1_483_032, 0.113), (None, 0.123)],
            "single": [(11_054, 0.01), (26_210, 0.02), (41_369, 0.04), (57_430, 0.06), (72_586, 0.08), (370_758, 0.093), (444_909, 0.103), (741_516, 0.113), (None, 0.123)],
        },
        "millionaire_surtax": 0.01,  # mental-health services tax above $1M
        "payroll": 0.012,  # SDI, no wage cap
    },
    "WA": {"deduction": {"mfj": 0, "single": 0}, "brackets": {"mfj": [(None, 0.0)], "single": [(None, 0.0)]}, "payroll": 0.0058},  # WA Cares
    "NY": {
        "deduction": {"mfj": 16_050, "single": 8_000},
        "brackets": {
            "mfj": [(17_150, 0.04), (23_600, 0.045), (27_900, 0.0525), (161_550, 0.055), (323_200, 0.06), (2_155_350, 0.0685), (5_000_000, 0.0965), (25_000_000, 0.103), (None, 0.109)],
            "single": [(8_500, 0.04), (11_700, 0.045), (13_900, 0.0525), (80_650, 0.055), (215_400, 0.06), (1_077_550, 0.0685), (5_000_000, 0.0965), (25_000_000, 0.103), (None, 0.109)],
        },
        "payroll": 0.0,
    },
}
NYC = {"mfj": [(21_600, 0.03078), (45_000, 0.03762), (90_000, 0.03819), (None, 0.03876)],
       "single": [(12_000, 0.03078), (25_000, 0.03762), (50_000, 0.03819), (None, 0.03876)]}


def tax_us(gross: float, state: str, filing: str = "mfj") -> dict:
    deduction, brackets = US_FEDERAL[filing]
    federal = progressive(max(0.0, gross - deduction), brackets)
    fica = 0.062 * min(gross, US_SS_WAGE_BASE) + 0.0145 * gross
    fica += 0.009 * max(0.0, gross - (250_000 if filing == "mfj" else 200_000))
    city = state == "NY_NYC"
    rules = US_STATES["NY" if city else state]
    taxable = max(0.0, gross - rules["deduction"][filing])
    state_tax = progressive(taxable, rules["brackets"][filing])
    state_tax += rules.get("millionaire_surtax", 0) * max(0.0, taxable - 1_000_000)
    state_tax += rules["payroll"] * gross
    if city:
        state_tax += progressive(taxable, NYC[filing])
    return {"federal income tax": federal, "social security + medicare": fica, "state/local": state_tax}


# --- Canada (2026, approximate) --------------------------------------------------------------------

CA_FEDERAL = [(58_523, 0.14), (117_045, 0.205), (181_440, 0.26), (258_482, 0.29), (None, 0.33)]
CA_FEDERAL_BPA = 16_452
PROVINCES = {
    "ON": {"brackets": [(53_891, 0.0505), (107_785, 0.0915), (150_000, 0.1116), (220_000, 0.1216), (None, 0.1316)],
           "bpa": 12_747, "surtax": [(5_710, 0.20), (7_307, 0.36)], "health_premium": 900},
    "BC": {"brackets": [(50_363, 0.0506), (100_728, 0.077), (115_648, 0.105), (140_430, 0.1229), (190_405, 0.147), (265_545, 0.168), (None, 0.205)],
           "bpa": 12_932, "surtax": [], "health_premium": 0},
}


def tax_canada(gross: float, province: str) -> dict:
    federal = max(0.0, progressive(gross, CA_FEDERAL) - 0.14 * CA_FEDERAL_BPA)
    rules = PROVINCES[province]
    basic = max(0.0, progressive(gross, rules["brackets"]) - rules["brackets"][0][1] * rules["bpa"])
    provincial = basic + sum(rate * max(0.0, basic - threshold) for threshold, rate in rules["surtax"])
    provincial += rules["health_premium"]
    payroll = 0.0595 * max(0.0, min(gross, 74_600) - 3_500)  # CPP
    payroll += 0.04 * max(0.0, min(gross, 85_000) - 74_600)  # CPP2
    payroll += 0.0163 * min(gross, 68_900)  # EI
    return {"federal income tax": federal, "provincial income tax": provincial, "CPP + EI": payroll}


# --- Netherlands, Singapore, UK, UAE, India, Switzerland -------------------------------------------

NL_BOX1 = [(38_883, 0.3575), (78_426, 0.3756), (None, 0.495)]
NL_RULING_SALARY_CAP = 262_000


def tax_nl(gross: float, ruling_pct: float = 0.27) -> dict:
    """ruling_pct: expat allowance share (30% through 2026, 27% from 2027; 0 if not eligible)."""
    allowance = ruling_pct * min(gross, NL_RULING_SALARY_CAP)
    return {"income tax + national insurance (box 1)": progressive(gross - allowance, NL_BOX1),
            "_tax_free_allowance": allowance}


SG_RESIDENT = [(20_000, 0.0), (30_000, 0.02), (40_000, 0.035), (80_000, 0.07), (120_000, 0.115), (160_000, 0.15),
               (200_000, 0.18), (240_000, 0.19), (280_000, 0.195), (320_000, 0.20), (500_000, 0.22),
               (1_000_000, 0.23), (None, 0.24)]


def tax_sg(gross: float) -> dict:
    return {"income tax": progressive(gross, SG_RESIDENT)}  # Employment Pass holders don't pay CPF


def tax_uk(gross: float) -> dict:
    allowance = max(0.0, 12_570 - max(0.0, gross - 100_000) / 2)
    taxable = max(0.0, gross - allowance)
    income = 0.20 * min(taxable, 37_700) + 0.40 * max(0.0, min(taxable, 125_140) - 37_700) + 0.45 * max(0.0, taxable - 125_140)
    ni = 0.08 * max(0.0, min(gross, 50_270) - 12_570) + 0.02 * max(0.0, gross - 50_270)
    return {"income tax": income, "national insurance": ni}


def tax_ae(gross: float) -> dict:
    return {"income tax": 0.0}


IN_NEW_REGIME = [(400_000, 0.0), (800_000, 0.05), (1_200_000, 0.10), (1_600_000, 0.15), (2_000_000, 0.20),
                 (2_400_000, 0.25), (None, 0.30)]


def tax_in(gross: float) -> dict:
    taxable = max(0.0, gross - 75_000)  # standard deduction, new regime
    base = progressive(taxable, IN_NEW_REGIME)
    surcharge = 0.25 if taxable > 20_000_000 else 0.15 if taxable > 10_000_000 else 0.10 if taxable > 5_000_000 else 0.0
    return {"income tax incl. surcharge + 4% cess": base * (1 + surcharge) * 1.04}


CH_ZURICH_APPROX = [(50_000, 0.05), (100_000, 0.15), (200_000, 0.25), (None, 0.33)]  # federal+canton+city, married


def tax_ch(gross: float) -> dict:
    return {"income tax (approximate)": progressive(gross, CH_ZURICH_APPROX),
            "social security (AHV/IV/EO + ALV)": 0.053 * gross + 0.011 * min(gross, 148_200)}


def tax_breakdown(jurisdiction: str, gross_local: float, *, filing: str = "mfj", nl_ruling: bool = True) -> dict:
    kind, _, region = jurisdiction.partition(":")
    if kind == "us":
        return tax_us(gross_local, region, filing)
    if kind == "ca":
        return tax_canada(gross_local, region)
    if kind == "nl":
        return tax_nl(gross_local, 0.27 if nl_ruling else 0.0)
    return {"sg": tax_sg, "uk": tax_uk, "ae": tax_ae, "in": tax_in, "ch": tax_ch}[kind](gross_local)


# --- Offers and city comparison -----------------------------------------------------------------------

@dataclass
class OfferEstimate:
    city: str
    currency: str
    gross_local: float
    gross_usd: float
    tax_local: float
    net_local: float
    net_usd: float
    effective_tax_rate: float
    family_cost_usd: float
    savings_usd: float
    breakdown: dict


def find_location(name: str) -> tuple[str, dict]:
    data = config.locations()["locations"]
    key = name.strip().lower().replace(" ", "_")
    if key in data:
        return key, data[key]
    needle = name.strip().lower()
    for loc_key, loc in data.items():
        if needle in [a.lower() for a in loc.get("aliases", [])] or needle == loc["name"].lower():
            return loc_key, loc
    raise KeyError(f"unknown city {name!r}; known: {', '.join(data)}")


def fx(currency: str) -> float:
    rates = config.locations()["fx_to_usd"]
    if currency.upper() not in rates:
        raise KeyError(f"no FX rate for {currency}; add it to knowledge/locations.yaml")
    return float(rates[currency.upper()])


def estimate(city: str, gross: float, currency: str | None = None, *, filing: str = "mfj",
             nl_ruling: bool = True) -> OfferEstimate:
    """Take-home and savings for a total annual package `gross` (in `currency`, default the city's own)."""
    key, loc = find_location(city)
    local = loc["currency"]
    gross_local = gross * fx(currency or local) / fx(local)
    parts = tax_breakdown(loc["tax"], gross_local, filing=filing, nl_ruling=nl_ruling)
    tax = sum(v for k, v in parts.items() if not k.startswith("_"))
    net_local = gross_local - tax
    net_usd = net_local * fx(local)
    return OfferEstimate(
        city=key, currency=local, gross_local=round(gross_local), gross_usd=round(gross_local * fx(local)),
        tax_local=round(tax), net_local=round(net_local), net_usd=round(net_usd),
        effective_tax_rate=round(tax / gross_local, 3) if gross_local else 0.0,
        family_cost_usd=loc["family_cost_usd"], savings_usd=round(net_usd - loc["family_cost_usd"]),
        breakdown={k: round(v) for k, v in parts.items()},
    )


def evaluate_offer(city: str, base: float, currency: str | None = None, bonus_pct: float = 0.0,
                   annual_equity: float = 0.0, sign_on: float = 0.0, *, nl_ruling: bool = True) -> dict:
    profile = config.profile()
    filing = (profile.get("household") or {}).get("us_filing", "mfj")
    total = base * (1 + bonus_pct / 100) + annual_equity
    offer = estimate(city, total, currency, filing=filing, nl_ruling=nl_ruling)
    current = profile.get("current") or {}
    result = {"offer": asdict(offer), "sign_on_usd": round(sign_on * fx(currency or offer.currency))}
    if current.get("total_comp") and current.get("city"):
        now = estimate(current["city"], current["total_comp"], current.get("currency"), filing=filing)
        result["current"] = asdict(now)
        result["savings_change_usd"] = offer.savings_usd - now.savings_usd
    target = (profile.get("targets") or {}).get("min_total_comp_usd")
    if target:
        result["vs_target_usd"] = offer.gross_usd - target
    return result


def compare(weights: dict[str, float] | None = None) -> list[dict]:
    data = config.locations()
    merged = {**data["weights"], **(weights or {})}
    total = sum(merged.values()) or 1.0
    merged = {k: v / total for k, v in merged.items()}
    rows = []
    for key, loc in data["locations"].items():
        score = sum(merged.get(c, 0) * loc["scores"].get(c, 0) for c in merged)
        mid = sum(loc["comp_band_usd"]) / 2
        est = estimate(key, mid, "USD")
        rows.append({
            "key": key, "name": loc["name"], "score": round(score, 2),
            "comp_band_usd": loc["comp_band_usd"], "net_at_mid_usd": est.net_usd,
            "effective_tax_rate": est.effective_tax_rate, "family_cost_usd": loc["family_cost_usd"],
            "savings_at_mid_usd": est.savings_usd, "parents": loc.get("parents", ""),
        })
    rows.sort(key=lambda r: -r["score"])
    return rows


def parse_weights(text: str) -> dict[str, float]:
    """'parents=0.3, comp=0.15' -> {'parents': 0.3, 'comp': 0.15}"""
    criteria = config.locations()["criteria"]
    weights = {}
    for item in filter(None, (part.strip() for part in (text or "").split(","))):
        name, _, value = item.partition("=")
        if name.strip() not in criteria:
            raise KeyError(f"unknown criterion {name.strip()!r}; choose from {', '.join(criteria)}")
        weights[name.strip()] = float(value)
    return weights


def _k(usd: float) -> str:
    return f"${usd / 1000:,.0f}K"


def render_comparison(rows: list[dict]) -> str:
    lines = ["| # | City | Score /10 | Typical comp (Director+) | Take-home at mid | Tax | Family cost | Savings at mid |",
             "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        low, high = r["comp_band_usd"]
        lines.append(f"| {i} | {r['name']} | {r['score']:.2f} | {_k(low)}–{_k(high)} | {_k(r['net_at_mid_usd'])} | "
                     f"{r['effective_tax_rate']:.0%} | {_k(r['family_cost_usd'])} | {_k(r['savings_at_mid_usd'])} |")
    return "\n".join(lines)


def render_offer(result: dict) -> str:
    o = result["offer"]
    lines = [
        f"Offer in {o['city']}: {o['gross_local']:,.0f} {o['currency']} total/yr (≈ {_k(o['gross_usd'])})",
        f"  Taxes: {o['tax_local']:,.0f} {o['currency']} ({o['effective_tax_rate']:.0%} effective)",
    ]
    lines += [f"    - {name.lstrip('_')}: {value:,.0f}" for name, value in o["breakdown"].items()]
    lines += [
        f"  Take-home: {o['net_local']:,.0f} {o['currency']} (≈ {_k(o['net_usd'])})",
        f"  Family cost estimate: {_k(o['family_cost_usd'])} → yearly savings ≈ {_k(o['savings_usd'])}",
    ]
    if result.get("sign_on_usd"):
        lines.append(f"  Sign-on (one-off, pre-tax): ≈ {_k(result['sign_on_usd'])}")
    if "current" in result:
        c = result["current"]
        lines.append(f"Current package: take-home ≈ {_k(c['net_usd'])}, savings ≈ {_k(c['savings_usd'])} "
                     f"→ change in yearly savings: {'+' if result['savings_change_usd'] >= 0 else ''}{_k(result['savings_change_usd'])}")
    if "vs_target_usd" in result:
        diff = result["vs_target_usd"]
        lines.append(f"Vs. total-comp target: {'+' if diff >= 0 else ''}{_k(diff)}")
    return "\n".join(lines)
