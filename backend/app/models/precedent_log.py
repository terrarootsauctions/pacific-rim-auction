"""
PrecedentLog model - stores a human's resolution to a flagged issue, keyed
strictly enough that only a genuinely IDENTICAL future case will match it.

The rule this implements (the architect's directive): the first time SI
encounters a type of issue, it has no precedent and must flag it for human
review. Once the architect (or an authorized compliance officer) resolves
it, that resolution is saved here. If the EXACT same situation recurs -
matched strictly on entity_type + issue_type + match_key - SI applies the
saved resolution automatically rather than re-flagging it. Anything that
isn't an exact match is treated as new and still goes to a human.

The match_key is deliberately strict and literal (e.g. a specific
combination of country_code + asset_category + failure_reason_code) -
never a fuzzy or semantic similarity match. A near-miss is not a match.
This is what keeps "apply what I decided before" from drifting into
"guess what I would decide now" - the exact failure mode the architect
and Claude discussed and explicitly want to avoid.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class PrecedentLog(Base):
    __tablename__ = "precedent_logs"

    id = Column(String, primary_key=True, default=gen_uuid)

    entity_type = Column(String, nullable=False, index=True)   # e.g. "jurisdiction_node", "asset"
    issue_type = Column(String, nullable=False, index=True)    # e.g. "check_failed", "suspicious_value"

    # The strict matching key - must match EXACTLY for this precedent to
    # apply automatically. Built from the specific dimensions that made
    # this case what it was (e.g. "country=ID|category=natural_resource|reason=no_disclosure_rule_found").
    match_key = Column(String, nullable=False, index=True)

    # What the human actually decided, in their own words/values - not an
    # inferred or paraphrased version of their reasoning.
    resolution_status = Column(String, nullable=False)   # the status/outcome they chose
    resolution_notes = Column(Text, nullable=True)

    resolved_by_user_id = Column(String, nullable=False)  # the real human who made this call
    resolved_at = Column(DateTime, default=datetime.utcnow)

    # Tracks how many times this precedent has been auto-applied since -
    # visible so the architect can see how much it's actually being used.
    times_applied = Column(Integer, default=0)

    def __repr__(self):
        return f"<PrecedentLog {self.entity_type}/{self.issue_type} key={self.match_key}>"
