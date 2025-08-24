# Remove the circular import
from app.models.user import User
from app.models.knowledge_base import (
    DBType,
    Credential, 
    Database,
    UserConnectionMap,
    KnowledgeBaseCategory,
    KnowledgeBaseMaster,
    KnowledgeBaseTableMap,
    KnowledgeBaseField,
    KnowledgeBaseAccess
)

# Export all models
__all__ = [
    "User",
    "Scheme",
    "Coupon",
    "CouponIssue",
    "Redemption",
    "Revenue",
    "Customer",
    "RaffleScheme",
    "Bill",
    "RaffleEntry",
    "RaffleWinner",
    # Knowledge Base Models
    "DBType",
    "Credential",
    "Database", 
    "UserConnectionMap",
    "KnowledgeBaseCategory",
    "KnowledgeBaseMaster",
    "KnowledgeBaseTableMap",
    "KnowledgeBaseField",
    "KnowledgeBaseAccess"
]
