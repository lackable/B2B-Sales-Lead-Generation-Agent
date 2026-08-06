"""Builder module for Shortlister Agent graph."""

from memory.checkpointer import get_checkpointer
from graph.shortlister import shortlister_builder

def build_graph(checkpointer=None):
    """
    Returns the compiled Shortlister Agent graph.
    Wraps the core graph with SqliteSaver for state persistence.
    """
    if checkpointer is None:
        checkpointer = get_checkpointer()
    
    return shortlister_builder.compile(checkpointer=checkpointer)
