"""Log and register the support-assist agent to Unity Catalog (v0.6 Step
6.4). Run only after test_agent.py has passed -- this creates a real UC
model version, not a disposable dev artifact.
"""
import mlflow
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksVectorSearchIndex
from agent import AGENT, LLM_ENDPOINT, TICKET_INDEX, REVIEW_INDEX

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/chiragvenkatesh92@gmail.com/novalake_genai_dev/support_assist_agent")

resources = [
    DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT),
    DatabricksVectorSearchIndex(index_name=TICKET_INDEX),
    DatabricksVectorSearchIndex(index_name=REVIEW_INDEX),
]

input_example = {
    "input": [{"role": "user", "content": "What are common reasons refunds take long?"}]
}

with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",
        input_example=input_example,
        resources=resources,
        pip_requirements=[
            "mlflow==3.6.0",
            "databricks-langchain",
            "langgraph==0.3.4",
            "pydantic",
            "databricks-agents",
        ],
    )
    print(f"Model URI: {model_info.model_uri}")

uc_model_info = mlflow.register_model(
    model_uri=model_info.model_uri,
    name="novalake.genai.support_assist_agent",
)
print(f"Registered: {uc_model_info.name} version {uc_model_info.version}")
