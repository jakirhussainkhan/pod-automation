"""Schema exports."""

from app.schemas.activity_log import ActivityLogRead
from app.schemas.ai import (
    AIStatusResponse,
    GeneratedContent,
    GeneratePostRequest,
    RegenerateCaptionRequest,
    VariationsRequest,
)
from app.schemas.ai_generation import AIGenerationRead
from app.schemas.app_setting import AppSettingRead, AppSettingUpdate
from app.schemas.automation import AutomationStatus
from app.schemas.common import ErrorResponse, MessageResponse, Page
from app.schemas.dashboard import DashboardStats
from app.schemas.facebook import FacebookStatus
from app.schemas.post import PostBase, PostCreate, PostRead, PostUpdate
from app.schemas.product import ProductBase, ProductCreate, ProductRead, ProductUpdate

__all__ = [
    "ActivityLogRead",
    "AIGenerationRead",
    "AIStatusResponse",
    "AppSettingRead",
    "AppSettingUpdate",
    "AutomationStatus",
    "DashboardStats",
    "ErrorResponse",
    "FacebookStatus",
    "GeneratedContent",
    "GeneratePostRequest",
    "MessageResponse",
    "Page",
    "PostBase",
    "PostCreate",
    "PostRead",
    "PostUpdate",
    "ProductBase",
    "ProductCreate",
    "ProductRead",
    "ProductUpdate",
    "RegenerateCaptionRequest",
    "VariationsRequest",
]
