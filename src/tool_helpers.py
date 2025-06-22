#!/usr/bin/env python3
"""
Helper functions for creating MCP tool input schemas.
Provides reusable utilities to reduce verbosity in schema definitions.
"""

from typing import Any, Dict, List


def create_schema(properties: Dict[str, Any], required: List[str] | None = None) -> Dict[str, Any]:
    """Helper function to create input schema with consistent structure"""
    return {
        "type": "object",
        "properties": properties,
        "required": required or []
    }


def string_property(description: str, default: str | None = None) -> Dict[str, Any]:
    """Helper function to create a string property"""
    prop = {
        "type": "string",
        "description": description
    }
    if default is not None:
        prop["default"] = default
    return prop


def array_property(description: str, item_type: str = "string", default: List[Any] | None = None) -> Dict[str, Any]:
    """Helper function to create an array property"""
    prop = {
        "type": "array",
        "items": {"type": item_type},
        "description": description
    }
    if default is not None:
        prop["default"] = default
    return prop


def code_property(description: str = "The code content to process") -> Dict[str, Any]:
    """Helper function to create a code property"""
    return string_property(description)


def language_property() -> Dict[str, Any]:
    """Helper function to create a language property"""
    return string_property(
        "Programming language (e.g., rust, python, javascript, typescript, etc.)",
        "auto-detect"
    )
