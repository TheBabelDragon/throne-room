"""Aurora Intent ↔ operator-ABI ActionProposal.

Aurora remains fail-closed. Redis ESCAPE still gates fire.
This module only translates schemas so SELF can see policy intents
and so ActionProposal can be journaled in Aurora's existing shape.

    from aurora.proposals import aurora_intent_to_proposal
"""

from agent.bridge import aurora_intent_to_proposal, proposal_to_aurora_action

__all__ = ["aurora_intent_to_proposal", "proposal_to_aurora_action"]
