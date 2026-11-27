"""Output models for the synthetic connector used by the contract tests."""
from pydantic import BaseModel


class Widget(BaseModel):
    id: str
    size: int


class WidgetPage(BaseModel):
    items: list[Widget]
    total: int


class ListWidgetsParams(BaseModel):
    name: str
