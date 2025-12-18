from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.nodes import (
    enrichment_node,
    build_queries_node,
    retrieve_node,
    score_node,
    output_node,
)

def create_agent_graph():
    """ Create the LangGraph workflow for domain comparable search. """

    workflow = StateGraph(AgentState)

    # ADD Nodes
    workflow.add_node("enrichment", enrichment_node)
    workflow.add_node("build_queries", build_queries_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("score", score_node)
    workflow.add_node("output", output_node)

    # Define edges 
    workflow.set_entry_point("enrichment")
    workflow.add_edge("enrichment", "build_queries")
    workflow.add_edge("build_queries", "retrieve")
    workflow.add_edge("retrieve", "score")
    workflow.add_edge("score", "output")
    workflow.add_edge("output", END)

    # compile graph
    app = workflow.compile()

    return app