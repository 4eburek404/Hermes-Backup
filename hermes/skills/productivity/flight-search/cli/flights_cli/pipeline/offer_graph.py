"""Public compatibility surface for the offer-graph pipeline.

Graph construction, materialization, merging, and the graph model each have a
single implementation in their dedicated modules.
"""

from .offer_graph_builder import OfferGraphBuilder, build_offer_graph
from .offer_graph_materializer import materialize_offer_graph_candidates
from .offer_graph_model import (
    OFFER_CANDIDATE_ENVELOPE_SCHEMA_VERSION,
    OFFER_GRAPH_SCHEMA_VERSION,
    OfferGraph,
)

__all__ = [
    "OFFER_CANDIDATE_ENVELOPE_SCHEMA_VERSION",
    "OFFER_GRAPH_SCHEMA_VERSION",
    "OfferGraph",
    "OfferGraphBuilder",
    "build_offer_graph",
    "materialize_offer_graph_candidates",
]
