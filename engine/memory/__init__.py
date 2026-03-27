"""
Creative Memory — persistent knowledge base that accumulates across generation cycles.

Three-layer architecture:
1. StatisticalMemory — from regression (quantitative backbone)
2. EditorialMemory — from human review (qualitative signal)
3. MarketMemory — from deployment/competitive signals (context awareness)
"""

from engine.memory.models import (
    CreativeMemory,
    StatisticalMemory,
    EditorialMemory,
    MarketMemory,
    GenerationContext,
    PatternInsight,
    ApprovalCluster,
    RejectionRule,
    FatigueAlert,
)
from engine.memory.builder import MemoryBuilder
from engine.memory.creative_memory import CreativeMemoryManager
from engine.memory.playbook_translator import PlaybookTranslator

__all__ = [
    "CreativeMemory",
    "StatisticalMemory",
    "EditorialMemory",
    "MarketMemory",
    "GenerationContext",
    "PatternInsight",
    "ApprovalCluster",
    "RejectionRule",
    "FatigueAlert",
    "MemoryBuilder",
    "CreativeMemoryManager",
    "PlaybookTranslator",
]
