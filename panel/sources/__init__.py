"""Turning Home Assistant state into the panel's data model.

Each module owns one region and returns finished model objects -- the renderer
makes no decisions. That keeps the commute rules and the bin window testable
without a display, and means an unreachable calendar costs one empty block
rather than the whole panel.
"""
