"""Deploy the registered support-assist agent to a Model Serving endpoint
(v0.6 Step 6.4). Runs as an ad-hoc job task (via manage_jobs/manage_job_runs)
since agents.deploy() takes ~15 min and would time out a synchronous call.
Not expressed as bundle IaC: agents.deploy() provisions more than a plain
model_serving_endpoints resource captures (Review App, inference tables, a
co-served feedback model, MLflow tracing wiring) -- see docs/06-genai.md
Step 6.4 for the retrofit-vs-script-pair decision. scale_to_zero trades
idle cost for first-query latency after a cold start -- pair with
teardown_agent.py for full teardown between work sessions if idle cost
still matters. This Free Edition workspace requires scale_to_zero=True on
every served model, not just as a cost optimization -- deploy() rejects
the request otherwise.
"""
import sys
import mlflow
from databricks import agents

model_name = sys.argv[1] if len(sys.argv) > 1 else "novalake.genai.support_assist_agent"
version = sys.argv[2] if len(sys.argv) > 2 else "1"
endpoint_name = sys.argv[3] if len(sys.argv) > 3 else "novalake-support-assist"

mlflow.set_experiment("/Users/chiragvenkatesh92@gmail.com/novalake_genai_dev/support_assist_agent")

print(f"Deploying {model_name} version {version} to endpoint {endpoint_name}...")
deployment = agents.deploy(
    model_name,
    version,
    endpoint_name=endpoint_name,
    scale_to_zero=True,
    tags={"source": "claude-code", "module": "v0.6-genai", "step": "6.4"},
)
print("Deployment complete!")
print(f"Endpoint name: {deployment.endpoint_name}")
print(f"Query URL: {deployment.query_endpoint}")
