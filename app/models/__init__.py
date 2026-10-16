"""Model exports and status enumerations."""

from enum import Enum

from app.models.activity_log import ActivityLog
from app.models.ai_generation import AIGeneration
from app.models.app_setting import AppSetting
from app.models.fb_account import AccountGroupBlocked, FbAccount
from app.models.group_lead import GroupLead
from app.models.group_post_queue import GroupPostQueue
from app.models.group_stats import GroupStats
from app.models.post import Post
from app.models.product import Product
from app.models.system import AiUsage, DbBackup


class ProductStatus(str, Enum):
    """Allowed product status values."""

    active = "active"
    archived = "archived"


class PostStatus(str, Enum):
    """Allowed post status values."""

    draft = "draft"
    scheduled = "scheduled"
    publishing = "publishing"
    published = "published"
    failed = "failed"


__all__ = [
    "ActivityLog",
    "AccountGroupBlocked",
    "AIGeneration",
    "AiUsage",
    "AppSetting",
    "DbBackup",
    "FbAccount",
    "GroupLead",
    "GroupPostQueue",
    "GroupStats",
    "Post",
    "PostStatus",
    "Product",
    "ProductStatus",
]
