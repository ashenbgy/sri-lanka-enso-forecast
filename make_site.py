"""Publish the notebook's results.zip in readable form:
  - README.md  "Results" section (plain-language summary, charts, tables, Sinhala summary)
  - images/    the charts used by the README
  - docs/index.html  interactive results page

Usage:  python3 make_site.py [path/to/results.zip]      (default: output/results.zip)
"""
import csv, io, json, re, sys, zipfile
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
zip_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "output" / "results.zip"
z = zipfile.ZipFile(zip_path)

def rows(name):
    return list(csv.reader(io.TextIOWrapper(z.open(name), "utf-8")))

def num(v):
    try:
        return float(v)
    except ValueError:
        return v

def records(name):
    head, *body = rows(name)
    return [dict(zip(head, map(num, r))) for r in body]

def matrix(name):
    head, *body = rows(name)
    return {"columns": head[1:], "rows": [[r[0]] + [float(x) for x in r[1:]] for r in body]}

def iso(d):
    return d[:10]

all_months = records("monthly_dataset.csv")
history = [{"month": iso(r[""]), "oni": r["oni"]} for r in all_months]
forecast = records("oni_forecast.csv")
rain = records("sri_lanka_rain_outlook.csv")
for r in forecast + rain:
    r["month"] = iso(r["month"])

data = {
    "generated": date.today().isoformat(),
    "last_month": history[-1]["month"],
    "last_oni": history[-1]["oni"],
    "record": max(history, key=lambda r: r["oni"]),
    "history": history[-36:],
    "forecast": forecast,
    "rain": rain,
    "skill": records("forecast_skill.csv"),
    "risk": matrix("regional_risk.csv"),
    "corr": matrix("rain_vs_oni_by_month.csv"),
}
town_mm, town_p = matrix("sri_lanka_towns_rain_mm.csv"), matrix("sri_lanka_towns_chance_wetter.csv")
data["towns"] = {"months": [iso(r[0]) for r in town_mm["rows"]],      # rows = towns, cell = [mm, chance wetter]
                 "rows": [[t] + [[m[j + 1], p[j + 1]] for m, p in zip(town_mm["rows"], town_p["rows"])]
                          for j, t in enumerate(town_mm["columns"])]}

html = (HERE / "site" / "template.html").read_text(encoding="utf-8")
assert "__DATA__" in html
out = HERE / "docs" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(html.replace("__DATA__", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
print(f"wrote {out}  (data through {data['last_month']})")

# ── README "Results" section ──────────────────────────────────────────────────
IMAGES = ["5_sri_lanka_rain_outlook.png", "7_sri_lanka_map.png", "4_oni_forecast.png", "2_rain_vs_oni_by_month.png",
          "6_regional_risk.png", "3_forecast_skill.png"]
(HERE / "images").mkdir(exist_ok=True)
for name in IMAGES:
    (HERE / "images" / name).write_bytes(z.read(name))

mon = lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%b %Y")

def sgn(v, d=0):
    s = f"{abs(v):.{d}f}"
    return ("" if float(s) == 0 else "+" if v > 0 else "−") + s

def month_list(rows):
    names = [mon(r["month"]) for r in rows]
    return ", ".join(names) if names else "none"

NEAR = 20   # mm: smaller anomalies are called "near normal"
wet = [r for r in rain if r["rain_anomaly_mm"] >= NEAR]
dry = [r for r in rain if r["rain_anomaly_mm"] <= -NEAR]
peak = max(forecast, key=lambda r: r["oni_mean"])
end = forecast[-1]
record = max(all_months, key=lambda r: r["oni"])
skill = data["skill"]
gain = sum(r["Skill vs persistence"] for r in skill) / len(skill)
risk_cols = data["risk"]["columns"]
risk_peak = sorted(((r[0], r[-1]) for r in data["risk"]["rows"]), key=lambda x: -x[1])
very_high = [f"{n} ({v:.2f})" for n, v in risk_peak if v >= 0.50]
high = [f"{n} ({v:.2f})" for n, v in risk_peak if 0.35 <= v < 0.50]
sl_risk = next(v for n, v in risk_peak if n == "Sri Lanka")

def icon(v):
    return "🌧️ wetter" if v >= NEAR else "☀️ drier" if v <= -NEAR else "➖ near normal"

rain_table = "\n".join(
    f"| {mon(r['month'])} | {icon(r['rain_anomaly_mm'])} | {sgn(r['rain_anomaly_mm'])} mm "
    f"| {sgn(r['p10_mm'])} to {sgn(r['p90_mm'])} mm | {r['chance_wetter_than_normal']:.0%} |"
    for r in rain)

towns = matrix("sri_lanka_towns_rain_mm.csv")       # rows = months, columns = towns
town_head = "| Town | " + " | ".join(mon(iso(r[0]))[:3] + " " + r[0][2:4] for r in towns["rows"]) + " |"
town_table = "\n".join([town_head, "|---" + "|---:" * len(towns["rows"]) + "|"] + [
    f"| {t} | " + " | ".join(sgn(r[j + 1]) for r in towns["rows"]) + " |"
    for j, t in enumerate(towns["columns"])])

last = mon(data["last_month"])
section = f"""## Results

*Data through **{last}**. Updated {data['generated']}. This is a machine-learning forecast, not an
official one. Check NOAA CPC, IRI or the Sri Lanka Department of Meteorology before acting on it.*

### In short

- **El Niño is happening now.** The ONI (central-Pacific sea temperature anomaly) is
  **{sgn(data['last_oni'], 2)} °C** in {last}. The highest value since 1979 is {sgn(record['oni'], 2)} °C ({mon(iso(record['']))}).
- **The forecast:** El Niño peaks at about **{sgn(peak['oni_mean'], 2)} °C around {mon(peak['month'])}**
  and weakens to about {sgn(end['oni_mean'], 2)} °C by {mon(end['month'])}.
- **Sri Lanka:** wetter than normal in **{month_list(wet)}**. Drier than normal in **{month_list(dry)}**.
- **Accuracy:** on years the model never saw (2015 to today), its error is **{gain:.0%} smaller** than
  simply assuming "no change".

### Sri Lanka rainfall, next 12 months

![Sri Lanka rainfall outlook](images/5_sri_lanka_rain_outlook.png)

"Expected" is the difference from the normal rainfall for that month (1991–2020 average).

| Month | Outlook | Expected | Likely range (10–90 %) | Chance of wetter than normal |
|---|---|---:|---:|---:|
{rain_table}

### Town by town (5 km CHIRPS rainfall)

![Sri Lanka 5 km map: chance of a wetter-than-normal month](images/7_sri_lanka_map.png)

Green means a wetter-than-normal month is likely, and brown means drier. The table shows the expected
difference from normal rainfall in mm per month.

{town_table}

### El Niño forecast

![ONI forecast](images/4_oni_forecast.png)

Above **+0.5 °C** is El Niño, and below **−0.5 °C** is La Niña. The shaded band shows the likely range.

### Why Sri Lanka is forecast month by month

![El Niño effect on rainfall by month](images/2_rain_vs_oni_by_month.png)

Blue means El Niño brings **more** rain that month, and red means **less**. For Sri Lanka the effect
flips with the season: more rain around **October**, less from **January to April**. So the old rule
"El Niño = drought" is wrong for Sri Lanka.

### Which regions are most at risk

![Regional risk](images/6_regional_risk.png)

The numbers show the chance of an extreme (1-in-5) dry or wet month. The normal chance is **0.20**.
At the forecast peak:

- Very high risk: {", ".join(very_high) or "none"}
- High risk: {", ".join(high) or "none"}
- Sri Lanka: {sl_risk:.2f}. Over a whole year Sri Lanka's wet and dry effects balance out,
  so the month-by-month table above gives more information.

### How good is the model?

![Forecast skill](images/3_forecast_skill.png)

Lower error is better. The model (blue) beats both simple guesses at every lead time from 1 to 12 months.

### සිංහල සාරාංශය

- **දැන් El Niño තත්ත්වයක් තියෙනවා.** {last} ONI අගය **{sgn(data['last_oni'], 2)} °C**. 1979 සිට වැඩිම අගය {sgn(record['oni'], 2)} °C.
- **අනාවැකිය:** El Niño එක **{mon(peak['month'])}** පමණ වෙද්දී උපරිමයට (**{sgn(peak['oni_mean'], 2)} °C**) යනවා.
  ඊට පස්සේ {mon(end['month'])} වෙද්දී ඒක දුර්වල වෙනවා.
- **ශ්‍රී ලංකාව:** සාමාන්‍යයට වඩා **වැඩි වැසි**: {month_list(wet)}.
  සාමාන්‍යයට වඩා **අඩු වැසි / වියළි**: {month_list(dry)}.
- El Niño එක ලංකාවේ වැසි වලට බලපාන විදිය කාලය අනුව වෙනස් වෙනවා. ඔක්තෝබර් කාලයේ වැසි වැඩි වෙනවා,
  ජනවාරි–අප්‍රේල් කාලයේ වියළි වෙනවා.
- Model එක පුහුණු කරද්දී පාවිච්චි නොකරපු 2015 සිට අද දක්වා දත්ත වලින් test කළාම,
  ඒකේ වැරදි "කිසිම වෙනසක් නැහැ" කියන අනුමානයට වඩා **{gain:.0%} කින් අඩුයි**.
- මේක නිල අනාවැකියක් නෙවෙයි. තීරණ ගන්න කලින් කාලගුණ විද්‍යා දෙපාර්තමේන්තුවේ අනාවැකි බලන්න.
"""

readme_path = HERE / "README.md"
readme = readme_path.read_text(encoding="utf-8")
START, END = "<!-- results:start -->", "<!-- results:end -->"
block = f"{START}\n{section}{END}"
if START in readme:
    readme = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, readme, flags=re.S)
else:
    readme = readme.replace("\n## Run it", f"\n{block}\n\n## Run it", 1)
readme_path.write_text(readme, encoding="utf-8")
print(f"updated {readme_path} Results section + images/")
