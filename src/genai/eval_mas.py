"""Offline evaluation for the text-to-SQL Supervisor Agent (v0.6 Step 6.8).

Unlike Step 6.5's agent, the MAS isn't a locally importable Python object --
it's an Agent-Bricks-managed resource, so predict_fn queries the deployed
mas-1b6eda83-endpoint directly. Per the databricks-mlflow-evaluation skill,
querying a deployed endpoint for eval is the documented exception to
"test locally first": production monitoring/quality tracking of a surface
that has no local equivalent.
"""
import mlflow
from mlflow.genai.scorers import Correctness, Safety
from databricks.sdk import WorkspaceClient
import requests

from sql_eval_dataset import SQL_EVAL_QUESTIONS

mlflow.set_experiment("/Users/chiragvenkatesh92@gmail.com/novalake_genai_dev/sql_agent_eval")

ENDPOINT_NAME = "mas-1b6eda83-endpoint"

w = WorkspaceClient()
HOST = w.config.host
HEADERS = w.config.authenticate()


def predict_fn(query):
    resp = requests.post(
        f"{HOST}/serving-endpoints/{ENDPOINT_NAME}/invocations",
        headers=HEADERS,
        json={"input": [{"role": "user", "content": query}]},
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    text_parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text_parts.append(c.get("text", ""))
    return {"response": "\n".join(text_parts)}


print("Running text-to-SQL eval against the deployed MAS endpoint...")
results = mlflow.genai.evaluate(
    data=SQL_EVAL_QUESTIONS,
    predict_fn=predict_fn,
    scorers=[Safety(), Correctness()],
)
print(f"Eval run ID: {results.run_id}")
print(f"Eval metrics: {results.metrics}")
