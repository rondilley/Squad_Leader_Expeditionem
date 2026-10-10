"""The 3D desktop board view (a Panda3D consumer of the host protocol).

This package is a new consumer of the same board document and view document the pygame
window reads. It holds no rule and no rule table (AR-06). It builds the board as a set of
hex prisms that the elevation of each hex lifts, so a hill is a thing the eye sees in three
dimensions.

The 3D view needs the `view3d` extra:

    pip install -e ".[view3d]"
"""
