#!/usr/bin/env python3
"""
NovaPay-style payments platform event generator.

Produces a deliberately messy, polymorphic, schema-drifting NDJSON event
stream intended as the RAW (Bronze) landing data for a Databricks
medallion -> serving -> GenAI learning project.

Design goals (the "challenges" baked into the data):
  - Polymorphic events: a shared envelope + an event-type-specific `payload`.
  - Schema drift across `schema_version` 1.0 vs 2.0 (renamed keys, unit
    changes, epoch-millis vs ISO timestamps, struct vs string source).
  - Nested arrays for EXPLODE practice (line_items, messages, documents,
    signals, fees, tags).
  - Rich free text (support tickets, message threads, reviews, risk notes)
    so the SAME curated data can later feed a GenAI / RAG layer.
  - Real-world data-quality defects (dupes, nulls, mixed casing,
    numbers-as-strings, out-of-range timestamps, malformed nested values).

Output: payments_events.json  (newline-delimited JSON, one event per line)
"""

import json
import random
import uuid
import datetime as dt

SEED = 42
random.seed(SEED)

N_EVENTS = 7000
START = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 6, 15, tzinfo=dt.timezone.utc)

# ---------------------------------------------------------------------------
# Pools (all original text)
# ---------------------------------------------------------------------------

CURRENCIES_CLEAN = ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"]
CURRENCIES_DIRTY = ["usd", "Usd", "eur", "Inr", "US$", " GBP", "jpy "]  # casing/invalid/whitespace

COUNTRIES = ["US", "us", "USA", "United States", "GB", "uk", "IN", "India",
             "CA", "Canada", "JP", "DE", "FR", None]

PAYMENT_METHODS = ["card", "wallet", "bank_transfer", "upi", "ach", "sepa"]
CARD_BRANDS = ["visa", "mastercard", "amex", "rupay", "discover"]

MERCHANT_NAMES = [
    "Aurora Books", "Northwind Grocers", "PixelForge Studio", "Cedar & Co",
    "Tokyo Bento House", "Helix Fitness", "Lumen Electronics", "Saffron Kitchen",
    "Drift Coffee", "Atlas Travel", "Verdant Plants", "Mosaic Apparel",
]
MERCHANT_CATEGORIES = ["retail", "food", "travel", "digital_goods", "services", "subscription"]

FIRST_NAMES = ["Maya", "Arjun", "Lena", "Hiro", "Sofia", "Daniel", "Priya",
               "Noah", "Yuki", "Omar", "Clara", "Ravi", "Elena", "Marco"]
LAST_NAMES = ["Tanaka", "Sharma", "Becker", "Rossi", "Khan", "Mueller",
              "Costa", "Iyer", "Novak", "Park", "Silva", "Reyes"]

DEVICE_OS = ["iOS 18.2", "Android 15", "Windows 11", "macOS 15", "Android 14"]
CHANNELS = ["email", "chat", "phone", "in_app"]
TICKET_TAGS = ["billing", "fraud", "login", "refund", "kyc", "payout",
               "dispute", "latency", "app_crash", "card_declined"]

# Support ticket subject + body templates (original)
TICKET_TEMPLATES = [
    ("Payment declined but money debited",
     "I tried to pay {amount} {cur} at {merchant} and the app showed a decline, "
     "but my bank account was still charged. The transaction reference does not appear "
     "in my history. Please reverse this and confirm by today."),
    ("Cannot log in after password reset",
     "After resetting my password I keep getting an 'unexpected error' on the {os} app. "
     "I have cleared the cache and reinstalled twice. I need access to dispute a charge "
     "from {merchant}."),
    ("Refund not received",
     "A refund for {amount} {cur} from {merchant} was approved {days} days ago but nothing "
     "has reached my account. The status in the app still says processing. How long does this take?"),
    ("Suspicious transaction on my account",
     "There is a {amount} {cur} payment to {merchant} that I did not make. I think my card "
     "details were stolen. Please freeze the card and open a fraud case."),
    ("Payout delayed for my store",
     "My merchant payout of {amount} {cur} was scheduled but is now two cycles late. My sellers "
     "are asking and I have no visibility into why it is held."),
    ("KYC documents rejected without reason",
     "I uploaded my passport and a utility bill but verification was rejected with no explanation. "
     "I have re-uploaded clearer scans. Can a human review this instead of the automated check?"),
    ("App charged me twice for one order",
     "I was billed {amount} {cur} twice for a single order at {merchant}. Both show as completed. "
     "Please refund the duplicate immediately."),
    ("Currency conversion looks wrong",
     "I was quoted one rate at checkout but charged a different total in {cur}. The difference is "
     "small but it keeps happening on every order from {merchant}."),
]

TICKET_REPLY_AGENT = [
    "Thanks for reaching out. I can see the pending hold and have escalated it to our payments team.",
    "I understand the frustration. I have opened a case and you should hear back within 24 hours.",
    "I have located the duplicate charge and submitted a reversal. It may take 3-5 business days.",
    "Your card has been temporarily blocked as a precaution. A new card request has been raised.",
    "I have asked our verification team to manually review the documents you uploaded.",
]
TICKET_REPLY_USER = [
    "Okay, thank you. Please keep me updated.",
    "That is still not acceptable, this has happened three times now.",
    "Great, I can see the reversal pending now. Appreciate the quick help.",
    "I have not heard anything yet, can you check the status again?",
    "Understood. I will wait for the email confirmation.",
]

REVIEW_TEMPLATES = [
    ("Fast and reliable", "Checkout was instant and the payout to my account came through the same day. "
                          "Have been using {merchant} for months with no issues."),
    ("Disappointing experience", "The payment kept failing on the {os} app and support took two days to reply. "
                                 "Expected better for the fees they charge."),
    ("Good but the fees add up", "Works well overall, though the currency conversion margin on {cur} orders "
                                 "is higher than competitors. Still, reliable for {merchant}."),
    ("Saved me during travel", "Used this abroad and it handled {cur} payments without any surprise blocks. "
                               "The fraud alerts were actually helpful and not annoying."),
    ("Refund took forever", "Getting a refund from {merchant} was painful. The money showed up eventually but "
                            "the status tracking was useless the whole time."),
    ("Smooth onboarding", "KYC was quick, took under ten minutes, and I was accepting payments the same afternoon. "
                          "Genuinely impressed."),
]

RISK_ALERT_TYPES = ["velocity", "geo_mismatch", "device_change", "amount_anomaly", "blacklist_match"]
RISK_NOTES = [
    "Multiple high-value attempts from a new device within minutes of login.",
    "Billing country and IP geolocation diverge by more than expected.",
    "Card tested with small amounts before a large purchase attempt.",
    "Account flagged on a shared watchlist; manual review recommended.",
    "Spending pattern deviates sharply from the customer's 90-day baseline.",
]

KYC_DOC_TYPES = ["passport", "drivers_license", "national_id", "utility_bill", "bank_statement"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_ts():
    delta = END - START
    secs = random.randint(0, int(delta.total_seconds()))
    return START + dt.timedelta(seconds=secs)

def iso(ts):
    return ts.isoformat().replace("+00:00", "Z")

def epoch_millis(ts):
    return int(ts.timestamp() * 1000)

def maybe(value, prob_missing=0.0, missing=None):
    """Return value, or `missing` with prob_missing (for optional/null fields)."""
    return missing if random.random() < prob_missing else value

def customer_id():
    return f"cust_{random.randint(10000, 19999)}"

def person_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def money_amount():
    return round(random.uniform(2.0, 980.0), 2)

def pick_currency():
    # 80% clean, 20% dirty
    return random.choice(CURRENCIES_CLEAN) if random.random() < 0.8 else random.choice(CURRENCIES_DIRTY)

def device_struct():
    return {
        "os": random.choice(DEVICE_OS),
        "ip": f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
        "device_id": "dev_" + uuid.uuid4().hex[:10],
        "trusted": random.choice([True, False]),
    }

def merchant_struct():
    return {
        "merchant_id": f"mer_{random.randint(1000, 1099)}",
        "name": random.choice(MERCHANT_NAMES),
        "category": random.choice(MERCHANT_CATEGORIES),
        "country": random.choice(COUNTRIES),
    }

# ---------------------------------------------------------------------------
# Payload builders (polymorphic by event_type)
# ---------------------------------------------------------------------------

def line_items():
    n = random.choice([0, 1, 1, 2, 2, 3, 4])  # some empty -> explode_outer territory
    items = []
    for _ in range(n):
        items.append({
            "sku": "SKU-" + uuid.uuid4().hex[:6].upper(),
            "qty": random.randint(1, 5),
            "unit_price": round(random.uniform(1.0, 200.0), 2),
            "tax_rate": random.choice([0.0, 0.05, 0.08, 0.18, 0.2]),
        })
    return items

def build_transaction(v2, status):
    cur = pick_currency()
    amount = money_amount()
    merchant = merchant_struct()
    items = line_items()

    risk = {
        "score": round(random.uniform(0, 1), 3),
        "flagged": random.random() < 0.12,
        "reasons": random.sample(RISK_ALERT_TYPES, k=random.randint(0, 2)),
    }
    # ~3% malformed: risk delivered as a string instead of struct
    if random.random() < 0.03:
        risk = "score=" + str(round(random.uniform(0, 1), 3))

    payment_method = {
        "type": random.choice(PAYMENT_METHODS),
        "brand": maybe(random.choice(CARD_BRANDS), 0.3, None),
        "last4": maybe(f"{random.randint(0,9999):04d}", 0.2, None),
    }

    base = {
        "merchant": maybe(merchant, 0.02, None),
        "payment_method": payment_method,
        "line_items": maybe(items, 0.05, None),  # sometimes the whole array is null/missing
        "risk": risk,
        "country": random.choice(COUNTRIES),
        "status": status,
        "idempotency_key": maybe("idem_" + uuid.uuid4().hex[:12], 0.4, None),
    }

    if v2:
        # v2: minor units integer + currency, customer_id, sometimes amount as STRING
        minor = int(round(amount * 100))
        base["amount_minor"] = str(minor) if random.random() < 0.1 else minor
        base["currency"] = cur
        base["customer_id"] = customer_id()
    else:
        # v1: major-unit float `amount`, legacy `cust_id`, currency lower freq
        base["amount"] = amount
        base["currency"] = cur
        base["cust_id"] = customer_id()
    return base

def build_refund(v2):
    return {
        "original_transaction_id": "txn_" + uuid.uuid4().hex[:12],
        "amount": maybe(money_amount(), 0.05, None),
        "currency": pick_currency(),
        "reason": random.choice([
            "customer_request", "duplicate_charge", "item_not_received",
            "fraudulent", "merchant_error",
        ]),
        "partial": random.choice([True, False]),
        ("customer_id" if v2 else "cust_id"): customer_id(),
        "notes": maybe("Refund approved after review.", 0.6, None),
    }

def build_payout(v2):
    n_fees = random.choice([0, 1, 2, 3])
    fees = [{
        "type": random.choice(["processing", "fx", "platform", "tax"]),
        "amount": round(random.uniform(0.1, 25.0), 2),
    } for _ in range(n_fees)]
    return {
        "merchant_id": f"mer_{random.randint(1000, 1099)}",
        "gross_amount": money_amount() * random.randint(2, 40),
        "currency": pick_currency(),
        "schedule": {
            "cycle": random.choice(["daily", "weekly", "monthly"]),
            "scheduled_for": iso(rand_ts()),
            "status": random.choice(["scheduled", "in_transit", "paid", "held"]),
        },
        "fees": fees,
        "bank_account_last4": maybe(f"{random.randint(0,9999):04d}", 0.15, None),
    }

def build_auth(v2):
    payload = {
        ("customer_id" if v2 else "cust_id"): customer_id(),
        "result": random.choice(["success", "success", "success", "failed", "challenged"]),
        "mfa_used": random.choice([True, False]),
        "geo": {
            "country": random.choice(COUNTRIES),
            "city": random.choice(["Chennai", "Tokyo", "London", "Toronto",
                                   "Berlin", "Mumbai", "Osaka", None]),
        },
    }
    if v2:
        payload["device"] = device_struct()
    else:
        # v1 flattened device fields instead of a struct
        d = device_struct()
        payload["device_os"] = d["os"]
        payload["device_id"] = d["device_id"]
    return payload

def build_kyc(v2):
    n = random.randint(1, 3)
    docs = [{
        "doc_type": random.choice(KYC_DOC_TYPES),
        "verified": random.choice([True, False]),
        "uploaded_at": iso(rand_ts()),
    } for _ in range(n)]
    return {
        ("customer_id" if v2 else "cust_id"): customer_id(),
        "full_name": person_name(),
        "status": random.choice(["approved", "rejected", "pending", "manual_review"]),
        "risk_score": round(random.uniform(0, 100), 1),
        "documents": docs,
    }

def build_support_ticket(v2):
    subject, body_tpl = random.choice(TICKET_TEMPLATES)
    fill = {
        "amount": money_amount(),
        "cur": random.choice(CURRENCIES_CLEAN),
        "merchant": random.choice(MERCHANT_NAMES),
        "os": random.choice(DEVICE_OS),
        "days": random.randint(2, 21),
    }
    description = body_tpl.format(**fill)

    # nested message thread (rich text for GenAI)
    n_msgs = random.randint(1, 5)
    messages = []
    t = rand_ts()
    for i in range(n_msgs):
        if i % 2 == 0:
            sender, body = "customer", description if i == 0 else random.choice(TICKET_REPLY_USER)
        else:
            sender, body = "agent", random.choice(TICKET_REPLY_AGENT)
        t = t + dt.timedelta(minutes=random.randint(5, 600))
        messages.append({"sender": sender, "timestamp": iso(t), "body_text": body})

    return {
        "ticket_id": "tkt_" + uuid.uuid4().hex[:10],
        ("customer_id" if v2 else "cust_id"): customer_id(),
        "channel": random.choice(CHANNELS),
        "priority": random.choice(["low", "medium", "high", "urgent"]),
        "subject": subject,
        "description": description,
        "tags": random.sample(TICKET_TAGS, k=random.randint(0, 3)),
        "related_transaction_id": maybe("txn_" + uuid.uuid4().hex[:12], 0.4, None),
        "messages": messages,
        "resolved": random.choice([True, False]),
        "resolution_minutes": maybe(random.randint(10, 4320), 0.3, None),
    }

def build_review(v2):
    title, body_tpl = random.choice(REVIEW_TEMPLATES)
    body = body_tpl.format(
        merchant=random.choice(MERCHANT_NAMES),
        os=random.choice(DEVICE_OS),
        cur=random.choice(CURRENCIES_CLEAN),
    )
    return {
        ("customer_id" if v2 else "cust_id"): customer_id(),
        "merchant_id": f"mer_{random.randint(1000, 1099)}",
        "rating": random.choice([1, 2, 3, 3, 4, 4, 5, 5, 5]),
        "title": title,
        "body": body,
        "helpful_votes": random.randint(0, 240),
        "verified_purchase": random.choice([True, False]),
    }

def build_risk_alert(v2):
    n_sig = random.randint(1, 4)
    signals = [{
        "name": random.choice(RISK_ALERT_TYPES),
        "weight": round(random.uniform(0, 1), 2),
        "value": round(random.uniform(0, 1000), 2),
    } for _ in range(n_sig)]
    return {
        ("customer_id" if v2 else "cust_id"): customer_id(),
        "alert_type": random.choice(RISK_ALERT_TYPES),
        "severity": random.choice(["info", "low", "medium", "high", "critical"]),
        "signals": signals,
        "notes": random.choice(RISK_NOTES),
        "auto_blocked": random.choice([True, False]),
    }

# ---------------------------------------------------------------------------
# Event type registry + weighted distribution
# ---------------------------------------------------------------------------

EVENT_PLAN = [
    ("transaction.completed", 0.30, lambda v2: build_transaction(v2, "completed")),
    ("transaction.failed",    0.10, lambda v2: build_transaction(v2, "failed")),
    ("transaction.created",   0.05, lambda v2: build_transaction(v2, "created")),
    ("support.ticket",        0.12, build_support_ticket),
    ("auth.session",          0.12, build_auth),
    ("review.submitted",      0.10, build_review),
    ("refund.issued",         0.06, build_refund),
    ("kyc.verification",      0.05, build_kyc),
    ("payout.scheduled",      0.05, build_payout),
    ("risk.alert",            0.05, build_risk_alert),
]
TYPES, WEIGHTS, BUILDERS = zip(*[(t, w, b) for t, w, b in EVENT_PLAN])

def build_envelope(event_type, builder):
    v2 = random.random() < 0.65  # ~65% schema 2.0, ~35% legacy 1.0
    ts = rand_ts()

    # Out-of-range / null timestamps for a small fraction (late/early arriving)
    r = random.random()
    if r < 0.02:
        ts_out = None
    elif r < 0.04:
        ts_out = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)   # epoch zero
    elif r < 0.05:
        ts_out = dt.datetime(2099, 12, 31, tzinfo=dt.timezone.utc)  # far future
    else:
        ts_out = ts

    env = {
        "event_id": "evt_" + uuid.uuid4().hex,
        "event_type": event_type,
        "schema_version": "2.0" if v2 else "1.0",
        "ingested_at": iso(dt.datetime.now(dt.timezone.utc)),
        "payload": builder(v2),
    }

    # Timestamp drift: v1 -> epoch millis (int), v2 -> ISO string
    if ts_out is None:
        env["event_timestamp"] = None
    elif v2:
        env["event_timestamp"] = iso(ts_out)
    else:
        env["event_timestamp"] = epoch_millis(ts_out)

    # Source drift: v1 string `source_system`, v2 struct `source`
    if v2:
        env["source"] = {
            "system": random.choice(["mobile-sdk", "web-checkout", "partner-api", "batch-import"]),
            "region": random.choice(["us-east", "eu-west", "ap-south", "ap-northeast"]),
            "host": "ingest-" + str(random.randint(1, 12)),
        }
    else:
        env["source_system"] = random.choice(["mobile-sdk", "web-checkout", "partner-api"])

    return env

# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def main():
    events = []
    for _ in range(N_EVENTS):
        idx = random.choices(range(len(TYPES)), weights=WEIGHTS, k=1)[0]
        events.append(build_envelope(TYPES[idx], BUILDERS[idx]))

    # Inject duplicate event_ids (replays) for ~1.5% -> dedup practice
    n_dupes = int(N_EVENTS * 0.015)
    for _ in range(n_dupes):
        src = random.choice(events)
        dup = json.loads(json.dumps(src))
        dup["ingested_at"] = iso(dt.datetime.now(dt.timezone.utc))  # later re-ingest
        events.append(dup)

    random.shuffle(events)

    out_path = "/home/claude/payments_events.json"
    with open(out_path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # --- quick stats for verification ---
    from collections import Counter
    type_counts = Counter(e["event_type"] for e in events)
    ver_counts = Counter(e["schema_version"] for e in events)
    null_ts = sum(1 for e in events if e["event_timestamp"] is None)
    id_counts = Counter(e["event_id"] for e in events)
    dup_ids = sum(1 for c in id_counts.values() if c > 1)

    import os
    size_mb = os.path.getsize(out_path) / (1024 * 1024)

    print(f"Total records written : {len(events)}")
    print(f"File size             : {size_mb:.2f} MB")
    print(f"Schema versions       : {dict(ver_counts)}")
    print(f"Null timestamps       : {null_ts}")
    print(f"Duplicated event_ids  : {dup_ids}")
    print("Event type counts     :")
    for t, c in type_counts.most_common():
        print(f"    {t:<24} {c}")

if __name__ == "__main__":
    main()
