"""Offline eval set for the text-to-SQL surface (v0.6 Step 6.8).

All expected_facts below come from actually executing the certified SQL in
docs/serving/question_catalog.md via execute_sql (2026-07-26) -- ground
truth by execution, not a guess. The first 6 questions are the certified
pairs named in docs/serving/genie_space.md's "Certified example question ->
SQL pairs" table (reused verbatim, with the exact catalog phrasing so the
answer is a fixed, date-unambiguous number -- the sample-question phrasing
"last quarter" would drift with today's date). The last 2 extend the set
with new text-to-SQL-specific cases per Step 6.8's objective.

Because the certified SQL is itself guardrail-compliant (count-weighted
rates recomputed from underlying counts, never an averaged rate column;
sources kept separate, never blended), a wrong/naive answer from the
text-to-SQL surface shows up as a Correctness mismatch against these facts
-- there's no need for a separate guardrail-behavior scorer duplicating
what Correctness against the right ground truth already catches.
"""

SQL_EVAL_QUESTIONS = [
    {
        "inputs": {"query": "What was our approval rate in Q1 2026, across both sources?"},
        "expectations": {
            "expected_facts": ["The approval rate is approximately 74.0% (0.740)"]
        },
    },
    {
        "inputs": {"query": "What's our overall refund rate, and how does it vary by source?"},
        "expectations": {
            "expected_facts": [
                "The multiline refund rate is approximately 21.5% (0.215)",
                "The ndjson refund rate is approximately 18.9% (0.189)",
            ]
        },
    },
    {
        "inputs": {"query": "What's our SLA breach rate by priority?"},
        "expectations": {
            "expected_facts": [
                "The urgent-priority SLA breach rate is approximately 54.4% (0.544), the highest of the four priorities",
                "The medium-priority SLA breach rate is approximately 38.5% (0.385), the lowest of the four priorities",
            ]
        },
    },
    {
        "inputs": {
            "query": "What fraction of transactions were risk-flagged, and separately, what fraction of risk alerts led to an auto-block, by source?"
        },
        "expectations": {
            "expected_facts": [
                "The ndjson transaction risk-flagged rate is approximately 12.4% (0.124)",
                "The multiline transaction risk-flagged rate is approximately 11.3% (0.113)",
                "The ndjson alert auto-block rate is approximately 56.2% (0.562)",
                "The multiline alert auto-block rate is approximately 46.1% (0.461)",
            ]
        },
    },
    {
        "inputs": {"query": "What's the average rating by merchant category?"},
        "expectations": {
            "expected_facts": [
                "The services category has the highest average rating, approximately 3.70",
                "The food category has the lowest average rating, approximately 3.54",
            ]
        },
    },
    {
        "inputs": {"query": "What's our authentication success rate, by MFA usage?"},
        "expectations": {
            "expected_facts": [
                "The success rate with MFA used is approximately 59.4% (0.594)",
                "The success rate without MFA is approximately 59.5% (0.595), nearly identical to the MFA-used rate",
            ]
        },
    },
    {
        "inputs": {"query": "What fraction of KYC verifications land in each status, by source?"},
        "expectations": {
            "expected_facts": [
                "For the multiline source, approved is the joint-highest status at approximately 27.5%",
                "For the ndjson source, rejected is the highest status at approximately 27.7%",
            ]
        },
    },
    {
        "inputs": {
            "query": "Which merchants have the most payouts on hold? How many merchants total have at least one held payout?"
        },
        "expectations": {
            "expected_facts": ["71 merchants have at least one payout in held status"]
        },
    },
]
