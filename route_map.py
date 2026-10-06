"""Interactive route map Streamlit component."""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component(
    "cx_route_map",
    path=str(Path(__file__).parent / "route_map_frontend"),
)


def route_map(points, mode, start_index=0, end_index=None, markers=None,
              segments=None, point_colors=None, key=None):
    """Render a route map and return a trim change or selected point."""
    return _component(
        points=points,
        mode=mode,
        start_index=start_index,
        end_index=end_index if end_index is not None else len(points) - 1,
        markers=markers or [],
        segments=segments or [],
        point_colors=point_colors or [],
        key=key,
        default=None,
    )
