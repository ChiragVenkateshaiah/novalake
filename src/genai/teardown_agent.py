"""Tear down the support-assist agent's serving deployment (v0.6 Step 6.4)
to eliminate idle cost between work sessions. Removes the serving endpoint,
Review App, inference tables, and co-served feedback model that
agents.deploy() created -- the underlying UC registered model version
(novalake.genai.support_assist_agent) is untouched, so re-running
deploy_agent.py later recreates the endpoint from the same model version.
"""
import sys
from databricks.agents import delete_deployment

model_name = sys.argv[1] if len(sys.argv) > 1 else "novalake.genai.support_assist_agent"
version = sys.argv[2] if len(sys.argv) > 2 else "1"

print(f"Deleting deployment for {model_name} version {version}...")
delete_deployment(model_name=model_name, model_version=version)
print("Deployment deleted.")
