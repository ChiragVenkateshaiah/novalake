"""Local smoke test for the support-assist agent (v0.6 Step 6.4).

Run with execute_code(file_path="test_agent.py") on the same cluster/
context the agent was uploaded to. Not a substitute for Step 6.5's
offline eval set -- this just confirms the agent runs end to end and
retrieves from both indexes before anything gets logged/registered.
"""
from agent import AGENT
from mlflow.types.responses import ResponsesAgentRequest, ChatContext

TEST_QUESTIONS = [
    "A customer says a refund was approved but the money never arrived. What similar tickets have we seen?",
    "What do customers say about payments failing while traveling abroad?",
    "What's the weather like in Paris?",  # should be refused -- no tool covers this
]

for q in TEST_QUESTIONS:
    request = ResponsesAgentRequest(
        input=[{"role": "user", "content": q}],
        context=ChatContext(user_id="test@novalake.local"),
    )
    result = AGENT.predict(request)
    print("=" * 80)
    print("Q:", q)
    for item in result.output:
        print(item.model_dump(exclude_none=True))
