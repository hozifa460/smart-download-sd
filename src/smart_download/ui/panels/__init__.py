"""
UI panel components and mixins for Smart Download.
"""
from .history_panel import HistoryPanelMixin
from .metrics_panel import MetricsPanelMixin
from .chunks_panel import ChunksPanelMixin
from .controls_panel import ControlsPanelMixin
from .inputs_panel import InputsPanelMixin

__all__ = [
    "HistoryPanelMixin",
    "MetricsPanelMixin",
    "ChunksPanelMixin",
    "ControlsPanelMixin",
    "InputsPanelMixin",
]
