"""All ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.db.models.analysis import AnalysisSession, Conversation, Message, QueryExecution, Report
from app.db.models.datasets import (
    Dataset,
    DatasetColumn,
    DatasetRelationship,
    DatasetTable,
    IngestionJob,
)
from app.db.models.identity import DatabaseConnection, User

__all__ = [
    "AnalysisSession",
    "Conversation",
    "DatabaseConnection",
    "Dataset",
    "DatasetColumn",
    "DatasetRelationship",
    "DatasetTable",
    "IngestionJob",
    "Message",
    "QueryExecution",
    "Report",
    "User",
]
