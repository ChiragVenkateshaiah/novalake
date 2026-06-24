#!/usr/bin/env python3
"""
NovaPay "paginated API export" generator -> multiLine JSON array.

Output shape (the whole file is ONE pretty-printed JSON ARRAY):

    [
      { page document 1 },
      { page document 2 },
      ...
    ]

Each page document is a deeply nested envelope:

    {
      "export_metadata": { ..., "record_counts": {dynamic map}, "checksums": {dynamic map} },
      "pagination":      { page, page_size, total_pages, cursor, next_cursor, has_more },
      "reference_data":  { merchants[], customers[], fx_rates[], currency_catalog{map} },
      "data":            { events[ ...polymorphic, 3-4 levels deep... ],
                           partial_failures[ ...DLQ records, alien schema... ] },
      "audit":           { warnings[], lineage[] }
    }

Read with:  spark.read.option("multiLine", "true").json(path)
-> yields ONE ROW PER PAGE. Everything else is explode + flatten + join + map-parse.

Deliberate, near-real complexity (see dataset_guide_multiline.md for the full list):
  - top-level array of pages (multiLine), one row per page
  - sibling arrays to explode from the same row (events, partial_failures, reference_data.*)
  - 3-4 levels of nesting (event.payload.transaction.line_items[].discounts[])
  - arrays-within-arrays (messages[].attachments[]) and arrays-OF-arrays (signal_matrix)
  - dynamic-key maps (metadata bag, balances, checksums, consents) -> schema-explosion trap
  - embedded dimensions with CROSS-PAGE drift (merchant name/category changes by page)
  - fx_rates table that must be applied to normalise currency
  - record_counts that intentionally disagree with actual array length (reconciliation)
  - stringified-JSON dead-letter records in partial_failures[] (from_json DLQ pattern)
  - schema drift v1/v2, mixed-type fields, malformed nested values, nulls/empties/missing
"""

import json
import random
import uuid
import datetime as dt

SEED = 43
random.seed(SEED)

N_PAGES = 9
EVENTS_PER_PAGE = (380, 520)   # randomised per page -> ~4,000+ events total
START = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 6, 15, tzinfo=dt.timezone.utc)

# ---------------------------------------------------------------------------
# Pools (original text)
# ---------------------------------------------------------------------------
CUR_CLEAN = ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"]
CUR_DIRTY = ["usd", "Usd", "eur", "Inr", "US$", " GBP", "jpy "]
COUNTRIES = ["US", "us", "USA", "United States", "GB", "uk", "IN", "India",
             "CA", "Canada", "JP", "DE", "FR", None]
PAY_METHODS = ["card", "wallet", "bank_transfer", "upi", "ach", "sepa"]
CARD_BRANDS = ["visa", "mastercard", "amex", "rupay", "discover"]
MERCHANT_NAMES = ["Aurora Books", "Northwind Grocers", "PixelForge Studio", "Cedar & Co",
                  "Tokyo Bento House", "Helix Fitness", "Lumen Electronics", "Saffron Kitchen",
                  "Drift Coffee", "Atlas Travel", "Verdant Plants", "Mosaic Apparel"]
MERCH_CATS = ["retail", "food", "travel", "digital_goods", "services", "subscription"]
FIRST = ["Maya", "Arjun", "Lena", "Hiro", "Sofia", "Daniel", "Priya", "Noah",
         "Yuki", "Omar", "Clara", "Ravi", "Elena", "Marco"]
LAST = ["Tanaka", "Sharma", "Becker", "Rossi", "Khan", "Mueller", "Costa",
        "Iyer", "Novak", "Park", "Silva", "Reyes"]
DEVICE_OS = ["iOS 18.2", "Android 15", "Windows 11", "macOS 15", "Android 14"]
CHANNELS = ["email", "chat", "phone", "in_app"]
TICKET_TAGS = ["billing", "fraud", "login", "refund", "kyc", "payout",
               "dispute", "latency", "app_crash", "card_declined"]
RISK_TYPES = ["velocity", "geo_mismatch", "device_change", "amount_anomaly", "blacklist_match"]
KYC_DOCS = ["passport", "drivers_license", "national_id", "utility_bill", "bank_statement"]
META_KEYS = ["campaign_id", "ab_bucket", "referrer", "app_build", "locale", "session_depth",
             "experiment", "utm_source", "risk_band", "queue", "retried", "partner_ref",
             "device_trust", "channel_hint", "promo_code"]

TICKET_TEMPLATES = [
    ("Payment declined but money debited",
     "I tried to pay {amount} {cur} at {merchant} and the app showed a decline, but my bank "
     "account was still charged. The reference does not appear in my history. Please reverse this."),
    ("Cannot log in after password reset",
     "After resetting my password I keep getting an 'unexpected error' on the {os} app. I have "
     "cleared the cache and reinstalled twice. I need access to dispute a charge from {merchant}."),
    ("Refund not received",
     "A refund for {amount} {cur} from {merchant} was approved {days} days ago but nothing has "
     "reached my account. The status in the app still says processing."),
    ("Suspicious transaction on my account",
     "There is a {amount} {cur} payment to {merchant} that I did not make. Please freeze the card "
     "and open a fraud case."),
    ("Payout delayed for my store",
     "My merchant payout of {amount} {cur} was scheduled but is now two cycles late and I have no "
     "visibility into why it is held."),
]
AGENT_REPLY = ["I can see the pending hold and have escalated it to our payments team.",
               "I have opened a case and you should hear back within 24 hours.",
               "I located the duplicate and submitted a reversal; it may take 3-5 business days.",
               "Your card has been temporarily blocked as a precaution."]
USER_REPLY = ["Okay, thank you. Please keep me updated.",
              "That is still not acceptable, this has happened three times now.",
              "Great, I can see the reversal pending now.",
              "I have not heard anything yet, can you check the status again?"]
REVIEW_TEMPLATES = [
    ("Fast and reliable", "Checkout was instant and the payout came through the same day. Reliable for {merchant}."),
    ("Disappointing", "The payment kept failing on the {os} app and support took two days to reply."),
    ("Good but fees add up", "Works well, though the conversion margin on {cur} orders is higher than competitors."),
    ("Saved me during travel", "Handled {cur} payments abroad without surprise blocks. Fraud alerts were helpful."),
]
RISK_NOTES = ["Multiple high-value attempts from a new device within minutes of login.",
              "Billing country and IP geolocation diverge by more than expected.",
              "Card tested with small amounts before a large purchase attempt.",
              "Spending deviates sharply from the customer's 90-day baseline."]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def rand_ts():
    secs = random.randint(0, int((END - START).total_seconds()))
    return START + dt.timedelta(seconds=secs)

def iso(ts): return ts.isoformat().replace("+00:00", "Z")
def epoch_ms(ts): return int(ts.timestamp() * 1000)
def maybe(v, p=0.0, m=None): return m if random.random() < p else v
def cust(): return f"cust_{random.randint(10000, 19999)}"
def name(): return f"{random.choice(FIRST)} {random.choice(LAST)}"
def amt(): return round(random.uniform(2.0, 980.0), 2)
def cur():  return random.choice(CUR_CLEAN) if random.random() < 0.8 else random.choice(CUR_DIRTY)

def dyn_metadata():
    """Dynamic-key map: a sparse subset of META_KEYS -> mixed-type values."""
    keys = random.sample(META_KEYS, k=random.randint(0, 5))
    out = {}
    for k in keys:
        out[k] = random.choice([
            random.randint(1, 9999),
            round(random.random(), 3),
            random.choice(["a", "b", "control", "variant", "true", "false", "en-US", "ja-JP"]),
            random.choice([True, False]),
        ])
    return out

def balances_map():
    """Dynamic-key map currency -> amount (schema-explosion trap)."""
    n = random.randint(0, 3)
    return {random.choice(CUR_CLEAN): round(random.uniform(0, 5000), 2) for _ in range(n)}

# ---------------------------------------------------------------------------
# Deeply nested payload builders
# ---------------------------------------------------------------------------
def discounts():
    return [{"code": "DISC" + uuid.uuid4().hex[:4].upper(),
             "type": random.choice(["percent", "flat", "loyalty"]),
             "value": round(random.uniform(0.5, 30.0), 2)}
            for _ in range(random.choice([0, 0, 1, 2]))]

def line_items():
    n = random.choice([0, 1, 1, 2, 3, 4])
    items = []
    for _ in range(n):
        items.append({
            "sku": "SKU-" + uuid.uuid4().hex[:6].upper(),
            "qty": random.randint(1, 5),
            "unit_price": round(random.uniform(1.0, 200.0), 2),
            "tax_rate": random.choice([0.0, 0.05, 0.08, 0.18, 0.2]),
            "discounts": discounts(),                       # array WITHIN array element
            "attributes": dyn_metadata(),                   # dynamic-key map nested deep
        })
    return items

def build_transaction(v2, status):
    risk = {"score": round(random.uniform(0, 1), 3),
            "flagged": random.random() < 0.12,
            "reasons": random.sample(RISK_TYPES, k=random.randint(0, 2)),
            # array-OF-arrays: a signal matrix
            "signal_matrix": [[round(random.random(), 2) for _ in range(random.randint(1, 3))]
                              for _ in range(random.randint(0, 3))]}
    if random.random() < 0.03:
        risk = "score=" + str(round(random.uniform(0, 1), 3))   # malformed: struct -> string

    pm = {"type": random.choice(PAY_METHODS),
          "brand": maybe(random.choice(CARD_BRANDS), 0.3),
          "last4": maybe(f"{random.randint(0,9999):04d}", 0.2),
          "network_tokens": [{"token": uuid.uuid4().hex[:16], "expires": iso(rand_ts())}
                             for _ in range(random.choice([0, 1, 2]))]}

    base = {
        "transaction": {                                   # extra nesting level
            "merchant_id": f"mer_{random.randint(1000, 1099)}",
            "payment_method": pm,
            "line_items": maybe(line_items(), 0.05),
            "fees": [{"kind": random.choice(["processing", "fx", "platform"]),
                      "amount": round(random.uniform(0.1, 12.0), 2)}
                     for _ in range(random.choice([0, 1, 2]))],
            "risk": risk,
        },
        "country": random.choice(COUNTRIES),
        "status": status,
        "balances": balances_map(),                        # dynamic-key map
        "metadata": dyn_metadata(),                        # dynamic-key map
        "idempotency_key": maybe("idem_" + uuid.uuid4().hex[:12], 0.4),
    }
    if v2:
        minor = int(round(amt() * 100))
        base["transaction"]["amount_minor"] = str(minor) if random.random() < 0.1 else minor
        base["transaction"]["currency"] = cur()
        base["customer_id"] = cust()
    else:
        base["transaction"]["amount"] = amt()
        base["transaction"]["currency"] = cur()
        base["cust_id"] = cust()
    return base

def build_support(v2):
    subj, tpl = random.choice(TICKET_TEMPLATES)
    desc = tpl.format(amount=amt(), cur=random.choice(CUR_CLEAN),
                      merchant=random.choice(MERCHANT_NAMES), os=random.choice(DEVICE_OS),
                      days=random.randint(2, 21))
    msgs = []
    t = rand_ts()
    for i in range(random.randint(1, 5)):
        sender, body = ("customer", desc if i == 0 else random.choice(USER_REPLY)) if i % 2 == 0 \
            else ("agent", random.choice(AGENT_REPLY))
        t += dt.timedelta(minutes=random.randint(5, 600))
        msgs.append({
            "sender": sender, "timestamp": iso(t), "body_text": body,
            "attachments": [{"file": "att_" + uuid.uuid4().hex[:6] + random.choice([".png", ".pdf"]),
                             "size_kb": random.randint(10, 4000)}
                            for _ in range(random.choice([0, 0, 1, 2]))],   # array WITHIN array
            "reactions": maybe({"agent": random.choice(["ack", "flag"])}, 0.7, {}),  # dynamic map
        })
    return {
        "ticket": {
            "ticket_id": "tkt_" + uuid.uuid4().hex[:10],
            "channel": random.choice(CHANNELS),
            "priority": random.choice(["low", "medium", "high", "urgent"]),
            "subject": subj, "description": desc,
            "tags": random.sample(TICKET_TAGS, k=random.randint(0, 3)),
            "messages": msgs,
            "sla": {"target_minutes": random.choice([60, 240, 1440]),
                    "breached": random.choice([True, False])},
            "related_transaction_id": maybe("txn_" + uuid.uuid4().hex[:12], 0.4),
        },
        ("customer_id" if v2 else "cust_id"): cust(),
        "metadata": dyn_metadata(),
    }

def build_review(v2):
    title, tpl = random.choice(REVIEW_TEMPLATES)
    body = tpl.format(merchant=random.choice(MERCHANT_NAMES), os=random.choice(DEVICE_OS),
                      cur=random.choice(CUR_CLEAN))
    return {
        "review": {
            "merchant_id": f"mer_{random.randint(1000, 1099)}",
            "rating": random.choice([1, 2, 3, 3, 4, 4, 5, 5, 5]),
            "title": title, "body": body,
            "media": [{"type": random.choice(["image", "video"]),
                       "url": "https://cdn.example/" + uuid.uuid4().hex[:8]}
                      for _ in range(random.choice([0, 1]))],
            "replies": [{"by": random.choice(["merchant", "moderator"]),
                         "text": random.choice(["Thanks for the feedback.", "We are looking into this."]),
                         "at": iso(rand_ts())}
                        for _ in range(random.choice([0, 0, 1]))],
        },
        ("customer_id" if v2 else "cust_id"): cust(),
        "verified_purchase": random.choice([True, False]),
    }

def build_auth(v2):
    p = {("customer_id" if v2 else "cust_id"): cust(),
         "result": random.choice(["success", "success", "success", "failed", "challenged"]),
         "mfa_used": random.choice([True, False]),
         "geo": {"country": random.choice(COUNTRIES),
                 "city": random.choice(["Chennai", "Tokyo", "London", "Toronto", None]),
                 "coordinates": [round(random.uniform(-90, 90), 4),
                                 round(random.uniform(-180, 180), 4)]}}   # array of scalars
    dev = {"os": random.choice(DEVICE_OS), "device_id": "dev_" + uuid.uuid4().hex[:10],
           "sensors": dyn_metadata()}                                     # dynamic-key map
    if v2:
        p["device"] = dev
    else:
        p["device_os"], p["device_id"] = dev["os"], dev["device_id"]
    return p

def build_kyc(v2):
    return {("customer_id" if v2 else "cust_id"): cust(),
            "full_name": name(),
            "status": random.choice(["approved", "rejected", "pending", "manual_review"]),
            "risk_score": round(random.uniform(0, 100), 1),
            "documents": [{"doc_type": random.choice(KYC_DOCS),
                           "verified": random.choice([True, False]),
                           "pages": [{"page_no": i + 1, "ocr_conf": round(random.random(), 2)}
                                     for i in range(random.randint(1, 3))]}     # array WITHIN array
                          for _ in range(random.randint(1, 3))]}

def build_refund(v2):
    return {"original_transaction_id": "txn_" + uuid.uuid4().hex[:12],
            "amount": maybe(amt(), 0.05), "currency": cur(),
            "reason": random.choice(["customer_request", "duplicate_charge", "fraudulent", "merchant_error"]),
            "partial": random.choice([True, False]),
            ("customer_id" if v2 else "cust_id"): cust()}

def build_payout(v2):
    return {"merchant_id": f"mer_{random.randint(1000, 1099)}",
            "gross_amount": amt() * random.randint(2, 40), "currency": cur(),
            "schedule": {"cycle": random.choice(["daily", "weekly", "monthly"]),
                         "scheduled_for": iso(rand_ts()),
                         "status": random.choice(["scheduled", "in_transit", "paid", "held"])},
            "line_breakdown": [{"merchant_order": "ord_" + uuid.uuid4().hex[:6],
                                "sub_items": [{"sku": "SKU-" + uuid.uuid4().hex[:5].upper(),
                                               "net": round(random.uniform(1, 200), 2)}
                                              for _ in range(random.randint(1, 3))]}  # array WITHIN array
                               for _ in range(random.choice([0, 1, 2]))]}

def build_risk(v2):
    return {("customer_id" if v2 else "cust_id"): cust(),
            "alert_type": random.choice(RISK_TYPES),
            "severity": random.choice(["info", "low", "medium", "high", "critical"]),
            "signals": [{"name": random.choice(RISK_TYPES),
                         "weight": round(random.random(), 2),
                         "sub_signals": [{"k": random.choice(["ip", "bin", "geo"]),
                                          "v": round(random.random(), 3)}
                                         for _ in range(random.randint(0, 2))]}   # array WITHIN array
                        for _ in range(random.randint(1, 4))],
            "notes": random.choice(RISK_NOTES),
            "auto_blocked": random.choice([True, False])}

EVENT_PLAN = [
    ("transaction.completed", 0.30, lambda v2: build_transaction(v2, "completed")),
    ("transaction.failed",    0.10, lambda v2: build_transaction(v2, "failed")),
    ("transaction.created",   0.05, lambda v2: build_transaction(v2, "created")),
    ("support.ticket",        0.12, build_support),
    ("auth.session",          0.12, build_auth),
    ("review.submitted",      0.10, build_review),
    ("refund.issued",         0.06, build_refund),
    ("kyc.verification",      0.05, build_kyc),
    ("payout.scheduled",      0.05, build_payout),
    ("risk.alert",            0.05, build_risk),
]
TYPES, WEIGHTS, BUILDERS = zip(*EVENT_PLAN)

def build_event():
    v2 = random.random() < 0.65
    idx = random.choices(range(len(TYPES)), weights=WEIGHTS, k=1)[0]
    etype, builder = TYPES[idx], BUILDERS[idx]
    ts = rand_ts()
    r = random.random()
    ts_out = None if r < 0.02 else (dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) if r < 0.04
             else (dt.datetime(2099, 12, 31, tzinfo=dt.timezone.utc) if r < 0.05 else ts))
    env = {"event_id": "evt_" + uuid.uuid4().hex, "event_type": etype,
           "schema_version": "2.0" if v2 else "1.0",
           "payload": builder(v2)}
    if ts_out is None:
        env["event_timestamp"] = None
    elif v2:
        env["event_timestamp"] = iso(ts_out)
    else:
        env["event_timestamp"] = epoch_ms(ts_out)        # mixed-type field across records
    if v2:
        env["source"] = {"system": random.choice(["mobile-sdk", "web-checkout", "partner-api"]),
                         "region": random.choice(["us-east", "eu-west", "ap-south", "ap-northeast"])}
    else:
        env["source_system"] = random.choice(["mobile-sdk", "web-checkout", "partner-api"])
    return env

# ---------------------------------------------------------------------------
# Embedded reference data (with CROSS-PAGE drift)
# ---------------------------------------------------------------------------
def merchants_for_page(page_no):
    out = []
    for mid in range(1000, 1100):
        if random.random() < 0.4:                # only a slice appears per page
            continue
        nm = random.choice(MERCHANT_NAMES)
        # drift: later pages sometimes change casing / category for same merchant_id
        if page_no > 0 and random.random() < 0.25:
            nm = nm.upper()
        out.append({
            "merchant_id": f"mer_{mid}",
            "name": nm,
            "category": random.choice(MERCH_CATS),
            "address": {"country": random.choice(COUNTRIES),
                        "geo": [round(random.uniform(-90, 90), 3),
                                round(random.uniform(-180, 180), 3)]},
            "tax_ids": {random.choice(["vat", "gst", "ein"]): uuid.uuid4().hex[:10]},  # dynamic map
            "as_of_page": page_no,
        })
    return out

def customers_for_page():
    out = []
    for _ in range(random.randint(40, 70)):
        out.append({
            "customer_id": cust(),
            "full_name": name(),
            "addresses": [{"type": random.choice(["home", "billing", "shipping"]),
                           "country": random.choice(COUNTRIES),
                           "primary": random.choice([True, False])}
                          for _ in range(random.randint(1, 3))],
            "loyalty": {"tier": random.choice(["bronze", "silver", "gold", None]),
                        "points": random.randint(0, 50000)},
            "consents": {c: random.choice([True, False])
                         for c in random.sample(["marketing", "data_share", "profiling"],
                                                k=random.randint(0, 3))},   # dynamic map
        })
    return out

def fx_rates_for_page():
    rates = []
    for q in CUR_CLEAN:
        if q == "USD":
            continue
        rates.append({"base": "USD", "quote": q,
                      "rate": round(random.uniform(0.5, 160.0), 4),
                      "as_of": iso(rand_ts())})
    return rates

def currency_catalog():
    return {c: {"decimals": 0 if c == "JPY" else 2, "symbol": "?"} for c in CUR_CLEAN}

def partial_failures():
    """Dead-letter records: alien schema; `raw` is a STRINGIFIED (escaped) JSON event."""
    out = []
    for _ in range(random.choice([0, 1, 2, 3])):
        bad = {"event_id": "evt_" + uuid.uuid4().hex, "event_type": "transaction.completed",
               "payload": {"transaction": {"amount": "NaN", "currency": None}}}  # genuinely broken
        out.append({
            "failure_id": "fail_" + uuid.uuid4().hex[:10],
            "stage": random.choice(["parse", "schema_validate", "enrich"]),
            "error_code": random.choice(["E_MALFORMED_JSON", "E_TYPE_MISMATCH", "E_MISSING_KEY"]),
            "raw": json.dumps(bad),                      # escaped JSON string -> from_json practice
            "attempted_at": iso(rand_ts()),
            "retryable": random.choice([True, False]),
        })
    return out

# ---------------------------------------------------------------------------
# Assemble pages
# ---------------------------------------------------------------------------
def build_page(page_no, total_pages):
    n_events = random.randint(*EVENTS_PER_PAGE)
    events = [build_event() for _ in range(n_events)]

    # ~1.5% replays within the page
    for _ in range(int(n_events * 0.015)):
        events.append(json.loads(json.dumps(random.choice(events))))
    random.shuffle(events)

    # record_counts INTENTIONALLY slightly disagree with reality (reconciliation exercise)
    reported = len(events) + random.choice([-3, -1, 0, 0, 2, 5])

    pf = partial_failures()
    cursor = "cur_" + uuid.uuid4().hex[:14]
    nxt = "cur_" + uuid.uuid4().hex[:14] if page_no < total_pages - 1 else None

    return {
        "export_metadata": {
            "export_id": "exp_" + uuid.uuid4().hex[:12],
            "generated_at": iso(dt.datetime.now(dt.timezone.utc)),
            "schema_version": "2.3",
            "source": {"system": "novapay-export-api", "region": random.choice(["us-east", "eu-west"])},
            "record_counts": {"events": reported, "partial_failures": len(pf),
                              "merchants": None, "customers": None},   # nulls + mismatch
            "checksums": {random.choice(["md5", "sha1", "crc32"]): uuid.uuid4().hex},  # dynamic map
        },
        "pagination": {"page": page_no + 1, "page_size": n_events, "total_pages": total_pages,
                       "cursor": cursor, "next_cursor": nxt, "has_more": page_no < total_pages - 1},
        "reference_data": {
            "merchants": merchants_for_page(page_no),
            "customers": customers_for_page(),
            "fx_rates": fx_rates_for_page(),
            "currency_catalog": currency_catalog(),       # dynamic-key map at reference level
        },
        "data": {"events": events, "partial_failures": pf},
        "audit": {
            "warnings": [{"code": random.choice(["W_LATE_ARRIVAL", "W_DUP_SEEN", "W_SCHEMA_DRIFT"]),
                          "detail": "auto-generated"} for _ in range(random.choice([0, 1, 2]))],
            "lineage": [{"stage": s, "at": iso(rand_ts())} for s in ["ingest", "export"]],
        },
    }

def main():
    pages = [build_page(i, N_PAGES) for i in range(N_PAGES)]

    out_path = "/home/claude/payments_events_multiline.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)   # pretty -> genuine multiLine document

    # stats
    import os
    total_events = sum(len(p["data"]["events"]) for p in pages)
    total_pf = sum(len(p["data"]["partial_failures"]) for p in pages)
    total_merch = sum(len(p["reference_data"]["merchants"]) for p in pages)
    total_cust = sum(len(p["reference_data"]["customers"]) for p in pages)
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"Pages                  : {len(pages)}")
    print(f"Total events           : {total_events}")
    print(f"Total partial_failures : {total_pf}")
    print(f"Total merchant rows     : {total_merch} (embedded dim, with cross-page drift)")
    print(f"Total customer rows     : {total_cust}")
    print(f"File size              : {size_mb:.2f} MB")

if __name__ == "__main__":
    main()
