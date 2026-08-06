from memory.checkpointer import get_checkpointer
from graph.contact_finder import contact_finder_builder

def build_graph(checkpointer=None):
    """
    Returns the compiled Contact Finder graph.
    Wraps the core graph with the checkpointer for state persistence.
    """
    if checkpointer is None:
        checkpointer = get_checkpointer()
    
    graph = contact_finder_builder.compile(checkpointer=checkpointer)
    return graph
