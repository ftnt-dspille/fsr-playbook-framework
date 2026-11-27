"""Synthetic connector models: the smallest package that honours the contract.

Relative imports are deliberate: the loader imports this package under a
private name, so absolute ``typed.`` imports would not resolve.
"""
from .models import ListWidgetsParams, Widget, WidgetPage

OPERATION_MODELS = {
    "list_widgets": (ListWidgetsParams, WidgetPage),
    "get_widget": Widget,
}
