"""Build evals/eval_set.jsonl: 69 real (Gemini-collected, spot-checked) + drafted questions.
Expected refunds are computed HERE by an independent re-implementation of the spec
(docs/refund_calculator_spec.md), not by importing src/tools/refund_calculator.py."""
import csv, json, sys
from decimal import Decimal as D, ROUND_HALF_UP

FLAT = {"1A": 240, "EC": 240, "2A": 200, "FC": 200, "3A": 180, "CC": 180, "3E": 180, "SL": 120, "2S": 60}

def expected_refund(cls, fare, hours, pax=1, quota="general", status="confirmed", train="normal", cancelled=False):
    fare = D(str(fare))
    if cancelled: ded = D(0)
    elif quota == "tatkal" and status == "confirmed": ded = fare
    elif status in ("rac", "waitlisted"): ded = min(fare, D(60)) if hours >= 0.5 else fare
    elif train == "vb":
        ded = fare * D("0.25") if hours > 72 else fare * D("0.5") if hours >= 8 else fare
    else:
        flat = D(FLAT[cls])
        if hours > 72: ded = flat
        elif hours >= 24: ded = max(fare * D("0.25"), flat)
        elif hours >= 8: ded = max(fare * D("0.5"), flat)
        else: ded = fare
        ded = min(ded, fare)
    ded = ded.quantize(D("0.01"), ROUND_HALF_UP)
    return str(((fare - ded) * pax).quantize(D("0.01")))

# (lang, question, kwargs for expected_refund)
REFUND = [
 ("en", "Cancelling my 3AC ticket of Rs 1850, 20 hours before departure. How much refund?", dict(cls="3A", fare=1850, hours=20)),
 ("en", "Sleeper ticket, fare 450, I want to cancel 30 hours before the train. Refund?", dict(cls="SL", fare=450, hours=30)),
 ("en", "2AC ticket cost me 2600. Train leaves in 5 days. If I cancel now how much do I get back?", dict(cls="2A", fare=2600, hours=120)),
 ("en", "How much refund for a 1A ticket of Rs 4800 cancelled 40 hours before departure?", dict(cls="1A", fare=4800, hours=40)),
 ("en", "Chair car ticket Rs 780, cancelling 10 hours before the train. What will I get back?", dict(cls="CC", fare=780, hours=10)),
 ("en", "I have a confirmed 3AC ticket of Rs 1200. Train is in 6 hours. Can I get anything back if I cancel?", dict(cls="3A", fare=1200, hours=6)),
 ("en", "Second sitting (2S) ticket of Rs 150, cancelling 4 days before. Refund amount?", dict(cls="2S", fare=150, hours=96)),
 ("en", "Sleeper fare Rs 320, cancelling 50 hours before departure. How much refund?", dict(cls="SL", fare=320, hours=50)),
 ("en", "EC ticket on Vande Bharat (day train, not sleeper) Rs 3200, cancelling 15 hours before. Refund?", dict(cls="EC", fare=3200, hours=15)),
 ("en", "3E (AC economy) ticket of Rs 1100 cancelled exactly 72 hours before departure - how much refund?", dict(cls="3E", fare=1100, hours=72)),
 ("en", "2AC Rs 2100, cancelling exactly 24 hours before the train leaves. Refund?", dict(cls="2A", fare=2100, hours=24)),
 ("en", "Sleeper Rs 600, I'm cancelling exactly 8 hours before departure. Do I get anything?", dict(cls="SL", fare=600, hours=8)),
 ("en", "Booked 3AC for 3 people, Rs 1500 each. Cancelling all 3 tickets 36 hours before. Total refund?", dict(cls="3A", fare=1500, hours=36, pax=3)),
 ("en", "Two sleeper tickets, Rs 480 per person, cancelling 2 days before (48 hours). How much will I get in total?", dict(cls="SL", fare=480, hours=48, pax=2)),
 ("en", "My RAC sleeper ticket cost Rs 520. I want to cancel 3 hours before the train. Refund?", dict(cls="SL", fare=520, hours=3, status="rac")),
 ("en", "Waitlisted 3AC ticket Rs 1650, cancelling 12 hours before departure. How much refund?", dict(cls="3A", fare=1650, hours=12, status="waitlisted")),
 ("en", "Waitlisted 2AC for 2 passengers, Rs 2300 each, cancelling 1 day before. Total refund?", dict(cls="2A", fare=2300, hours=24, pax=2, status="waitlisted")),
 ("en", "I have a confirmed Tatkal 3AC ticket of Rs 2100 and want to cancel 30 hours before. Refund?", dict(cls="3A", fare=2100, hours=30, quota="tatkal")),
 ("en", "Tatkal sleeper ticket is still waitlisted (Rs 700). If I cancel it 5 hours before the train, how much do I get?", dict(cls="SL", fare=700, hours=5, quota="tatkal", status="waitlisted")),
 ("en", "Railways cancelled my train. My 2AC ticket was Rs 2900. How much refund will I get?", dict(cls="2A", fare=2900, hours=10, cancelled=True)),
 ("en", "Vande Bharat Sleeper 3AC ticket Rs 2400, cancelling 4 days before. Refund?", dict(cls="3A", fare=2400, hours=96, train="vb")),
 ("en", "Vande Bharat Sleeper 2AC Rs 3100, cancelling 30 hours before departure. How much back?", dict(cls="2A", fare=3100, hours=30, train="vb")),
 ("en", "Amrit Bharat II sleeper ticket Rs 500, cancelling 6 hours before. Any refund?", dict(cls="SL", fare=500, hours=6, train="vb")),
 ("en", "Cheap 2S ticket of Rs 55, cancelling 3 days before departure (more than 72h). What do I get back?", dict(cls="2S", fare=55, hours=80)),
 ("en", "Sleeper ticket Rs 200 cancelled 30 hours before. Refund?", dict(cls="SL", fare=200, hours=30)),
 ("en", "1A ticket Rs 5200, cancelling 12 hours before departure. How much refund?", dict(cls="1A", fare=5200, hours=12)),
 ("en", "Confirmed CC ticket for Rs 1250, train in 2 hours. If I cancel, refund?", dict(cls="CC", fare=1250, hours=2)),
 ("en", "RAC 3AC ticket Rs 1400, cancelling 20 minutes before departure. Any refund?", dict(cls="3A", fare=1400, hours=0.33, status="rac")),
 ("hinglish", "3AC ka ticket 1850 ka hai, train 20 ghante baad hai. Cancel karu toh kitna paisa wapas milega?", dict(cls="3A", fare=1850, hours=20)),
 ("hinglish", "mera sleeper ka RAC ticket hai 450 rupaye ka, train 10 ghante baad hai, cancel karu toh kitna milega?", dict(cls="SL", fare=450, hours=10, status="rac")),
 ("hinglish", "2AC ticket 2500 ka liya tha, 4 din baad ki train hai. Abhi cancel karne pe kitna refund aayega?", dict(cls="2A", fare=2500, hours=96)),
 ("hinglish", "Sleeper ka confirm ticket 380 rs ka, train 30 ghante baad. Cancel karu toh kitna katega aur kitna milega?", dict(cls="SL", fare=380, hours=30)),
 ("hinglish", "bhai tatkal 3AC confirm ticket hai 1900 ka, 2 din baad train hai, cancel karne pe kuch milega?", dict(cls="3A", fare=1900, hours=48, quota="tatkal")),
 ("hinglish", "waiting ticket hai 2AC ka, 2200 rupaye, train 15 ghante baad. Cancel karu toh refund kitna?", dict(cls="2A", fare=2200, hours=15, status="waitlisted")),
 ("hinglish", "Chair car ka ticket 900 ka, train 12 ghante mein hai, cancel karne pe kitna milega?", dict(cls="CC", fare=900, hours=12)),
 ("hinglish", "3 logo ka sleeper ticket hai, har ek ka 420, train 3 din baad hai (80 ghante). Sab cancel karu toh total kitna wapas aayega?", dict(cls="SL", fare=420, hours=80, pax=3)),
 ("hinglish", "Train hi cancel ho gayi railway ki taraf se, mera sleeper ticket 600 ka tha. Kitna refund milega?", dict(cls="SL", fare=600, hours=5, cancelled=True)),
 ("hinglish", "1A ka ticket 4500 ka hai, train 7 ghante baad hai, cancel karu toh?", dict(cls="1A", fare=4500, hours=7)),
 ("hinglish", "Vande Bharat Sleeper ka 3AC ticket 2000 ka, train 10 ghante baad, cancel karu toh kitna milega?", dict(cls="3A", fare=2000, hours=10, train="vb")),
 ("hinglish", "3E ticket 1000 rupaye, 26 ghante pehle cancel kar raha hu, refund kitna?", dict(cls="3E", fare=1000, hours=26)),
]
# (lang, question, expected TDR rule)
TDR = [
 ("en", "My train is running 5 hours late and I don't want to travel anymore. What should I do to get my money back?", "T2"),
 ("en", "The AC in our 3AC coach stopped working for most of the journey. Can I get any refund?", "T3"),
 ("en", "Train was diverted and doesn't go through my boarding station now, so I didn't travel. Refund?", "T4"),
 ("en", "Our train was terminated 200 km before my destination. Can I get money back for the remaining part?", "T5"),
 ("en", "I booked 2AC but was given a 3AC berth by the TTE after the chart was made. How do I get the difference back?", "T6"),
 ("en", "I was asked to travel in a lower class than I booked so I refused and didn't travel. Can I get a refund?", "T7"),
 ("en", "We were 4 on one PNR but only 2 of us travelled. How do we get refund for the other 2?", "T8"),
 ("en", "My first train was late and I missed my connecting train. Both were on linked PNRs. What can I do?", "T9"),
 ("en", "Train was cancelled by railways. Do I need to file a TDR for my e-ticket?", "T1"),
 ("en", "I just decided not to travel today, train leaves in 3 hours. Should I file a TDR?", "T10"),
 ("hinglish", "Train 4 ghante late hai, main nahi jaana chahta. TDR kab tak file karna padega?", "T2"),
 ("hinglish", "AC coach ka AC pura raaste band tha, kuch paisa wapas milega kya? kab tak claim karna hai?", "T3"),
 ("hinglish", "linked PNR tha, pehli train late hui aur meri connecting train chhoot gayi. Refund milega?", "T9"),
 ("hinglish", "Counter se ticket liya tha, train 6 ghante late hai, main travel nahi karunga. Refund kaise milega?", "T2"),
]
MISSING = [
 ("en", "I want to cancel my ticket. How much refund will I get?", "no class, fare or timing"),
 ("en", "3AC ticket, cancelling tomorrow. Refund?", "no fare, unclear hours"),
 ("hinglish", "ticket cancel karna hai 1200 ka, kitna milega?", "no class or timing"),
 ("hinglish", "sleeper ticket hai, kal ki train, cancel karu toh refund?", "no fare, unclear hours"),
]
OOS = [
 ("en", "What is the PNR status of 4521367890?", "PNR lookup"),
 ("en", "Book me a 3AC ticket from Delhi to Mumbai for tomorrow.", "booking"),
 ("hinglish", "Rajdhani abhi kahan pahunchi hai?", "live train status"),
 ("en", "Which is the best biryani at Hyderabad station?", "unrelated"),
]
# stale traps WITH full details -> the answer must use the 2026 slabs
STALE = [
 ("en", "Under the 48-hour rule I should only lose the flat charge, right? My 3AC ticket is Rs 1600 and I'm cancelling 30 hours before.", dict(cls="3A", fare=1600, hours=30)),
 ("en", "I read cancelling between 12 and 4 hours before departure costs 50%. My sleeper ticket is Rs 500 and the train is in 6 hours. So I get Rs 250 back?", dict(cls="SL", fare=500, hours=6)),
 ("en", "Since I'm cancelling more than 48 hours before, only Rs 200 is cut for my 2AC ticket of Rs 2400, correct? It's 60 hours before departure.", dict(cls="2A", fare=2400, hours=60)),
 ("hinglish", "48 ghante se pehle cancel karne pe sirf flat charge katta hai na? Sleeper 450 ka hai, 50 ghante baaki hain.", dict(cls="SL", fare=450, hours=50)),
]

def row(i, sl, lang, q, origin, route, **kw):
    r = dict(id=i, slice=sl, lang=lang, question=q, origin=origin, expected_route=route,
             expected_refund=None, expected_tdr=None, in_docs=None, link=None, notes="")
    r.update(kw); return r

rows = []
# real rows from the triaged CSV
ROUTE = {"rule": ["retrieve"], "tdr": ["tdr_tool", "retrieve"], "out_of_scope": ["refuse"],
         "missing_info": ["ask_missing", "retrieve"], "stale_trap": ["retrieve", "ask_missing", "calculator"],
         "refund": ["calculator", "ask_missing"]}
for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")):
    if r["decision"] == "drop": continue
    extra = {}
    if r["id"] == "q018": extra["expected_refund"] = "0.00"
    if "CHECK" in r["review_note"]: extra["in_docs"] = "check"
    rows.append(row(r["id"], r["slice"], r["lang"], r["question"], "real", ROUTE[r["slice"]],
                    link=r["link"], notes=(r["notes"] + " | " + r["review_note"]).strip(" |"), **extra))
n = 0
def nid(p):
    global n; n += 1; return f"{p}{n:03d}"
for lang, q, kw in REFUND:
    rows.append(row(nid("d"), "refund", lang, q, "drafted", ["calculator"], expected_refund=expected_refund(**kw), params=kw))
for lang, q, t in TDR:
    rows.append(row(nid("d"), "tdr", lang, q, "drafted", ["tdr_tool"], expected_tdr=t))
for lang, q, why in MISSING:
    rows.append(row(nid("d"), "missing_info", lang, q, "drafted", ["ask_missing"], notes=why))
for lang, q, why in OOS:
    rows.append(row(nid("d"), "out_of_scope", lang, q, "drafted", ["refuse"], notes=why))
for lang, q, kw in STALE:
    rows.append(row(nid("d"), "stale_trap", lang, q, "drafted", ["calculator"], expected_refund=expected_refund(**kw), params=kw))

with open("eval_set.jsonl", "w", encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
import collections
print(len(rows), collections.Counter((r["slice"], r["origin"]) for r in rows))
print("hinglish", sum(r["lang"] == "hinglish" for r in rows))
for r in rows:
    if r.get("params"): print(r["id"], r["expected_refund"], r["params"])