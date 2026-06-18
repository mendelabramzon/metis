"""Skill category tags (the primary capability categories from the plan).

Categories are advisory metadata used for discovery/selection (Stage 10), not a security
boundary — the manifest's permissions are the security contract.
"""

from __future__ import annotations

from enum import StrEnum


class SkillCategory(StrEnum):
    DEEP_WEB_SEARCH = "deep_web_search"
    SPREADSHEET_ANALYSIS = "spreadsheet_analysis"
    WORD_REPORT_GENERATION = "word_report_generation"
    BROWSER_RESEARCH = "browser_research"
    DATA_CLEANUP = "data_cleanup"
    CHART_GENERATION = "chart_generation"
    CONNECTOR_ACTION = "connector_action"
    WIKI_FILE_BACK = "wiki_file_back"
    OTHER = "other"
