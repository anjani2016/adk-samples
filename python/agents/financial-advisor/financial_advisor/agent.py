# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Financial coordinator: provide reasonable investment strategies"""

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from . import prompt
from .sub_agents.data_analyst import data_analyst_agent
from .sub_agents.execution_analyst import execution_analyst_agent
from .sub_agents.risk_analyst import risk_analyst_agent
from .sub_agents.trading_analyst import trading_analyst_agent

MODEL = "gemini-2.5-pro"


financial_coordinator = LlmAgent(
    name="financial_coordinator",
    model=MODEL,
    description=(  # This description is for the model, used when this agent is a tool.
        "Guides a user through a structured financial advice process by "
        "orchestrating sub-agents to analyze tickers, develop trading "
        "strategies, define execution plans, and evaluate risk."
    ),
    # The 'instruction' is a system prompt that defines the agent's role,
    # personality, and the high-level plan it should follow.
    instruction=prompt.FINANCIAL_COORDINATOR_PROMPT,
    output_key="financial_coordinator_output",
    tools=[
        AgentTool(agent=data_analyst_agent),
        AgentTool(agent=trading_analyst_agent),
        AgentTool(agent=execution_analyst_agent),
        AgentTool(agent=risk_analyst_agent),
    ],
)

# The root_agent is the conventional entry point for the ADK to run this agent.
root_agent = financial_coordinator
