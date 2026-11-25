from typing import NewType
from uuid import UUID

ProjectId = NewType("ProjectId", UUID)
DocumentId = NewType("DocumentId", UUID)
ChunkId = NewType("ChunkId", UUID)
AgentId = NewType("AgentId", UUID)
EvalCaseId = NewType("EvalCaseId", UUID)
EvalRunId = NewType("EvalRunId", UUID)
ConversationId = NewType("ConversationId", UUID)
UserId = NewType("UserId", UUID)
