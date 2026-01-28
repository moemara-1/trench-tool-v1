"""
Trench Tool V1 - Volume Spike Detector
Identifies sudden volume increases that may indicate whale accumulation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass
from collections import deque

from models import Token, AlertPriority

logger = logging.getLogger(__name__)


@dataclass
class VolumeData:
    """Volume data point."""
    timestamp: datetime
    volume_sol: float
    volume_usd: float
    transaction_count: int


@dataclass
class VolumeSpike:
    """A detected volume spike event."""
    token_address: str
    detected_at: datetime
    current_volume_sol: float
    average_volume_sol: float
    spike_multiplier: float  # Current / Average
    period_minutes: int
    transaction_count: int
    is_significant: bool


class VolumeSpikeDetector:
    """
    Detects sudden volume increases.
    
    Features:
    - Rolling volume tracking
    - Spike detection with configurable thresholds
    - Transaction count correlation
    - Whale accumulation signals
    """
    
    def __init__(self):
        # Volume history per token (last 24h in 5-min buckets)
        self._volume_history: Dict[str, deque] = {}
        self._spikes: List[VolumeSpike] = []
        
        # Thresholds
        self.spike_threshold = 3.0  # 3x average = spike
        self.significant_spike_threshold = 5.0  # 5x = significant
        self.min_volume_for_alert = 5.0  # Min SOL volume
        self.history_buckets = 288  # 24h in 5-min intervals
    
    def add_volume(
        self,
        token_address: str,
        volume_sol: float,
        volume_usd: float = None,
        transaction_count: int = 1,
    ) -> Optional[VolumeSpike]:
        """
        Add volume data and check for spikes.
        
        Returns VolumeSpike if one is detected.
        """
        if token_address not in self._volume_history:
            self._volume_history[token_address] = deque(maxlen=self.history_buckets)
        
        now = datetime.utcnow()
        data = VolumeData(
            timestamp=now,
            volume_sol=volume_sol,
            volume_usd=volume_usd or volume_sol * 200,  # Rough SOL price
            transaction_count=transaction_count,
        )
        
        self._volume_history[token_address].append(data)
        
        # Check for spike
        return self._detect_spike(token_address)
    
    def _detect_spike(self, token_address: str) -> Optional[VolumeSpike]:
        """Check if recent volume constitutes a spike."""
        history = self._volume_history.get(token_address)
        if not history or len(history) < 12:  # Need at least 1h of data
            return None
        
        # Get recent volume (last 15 min)
        now = datetime.utcnow()
        recent_cutoff = now - timedelta(minutes=15)
        recent_data = [d for d in history if d.timestamp >= recent_cutoff]
        
        if not recent_data:
            return None
        
        recent_volume = sum(d.volume_sol for d in recent_data)
        recent_tx_count = sum(d.transaction_count for d in recent_data)
        
        # Get average volume (older data)
        older_data = [d for d in history if d.timestamp < recent_cutoff]
        if not older_data:
            return None
        
        avg_volume = sum(d.volume_sol for d in older_data) / len(older_data) * 3  # Normalize to 15 min
        
        if avg_volume <= 0:
            return None
        
        # Calculate spike multiplier
        multiplier = recent_volume / avg_volume
        
        # Check if spike
        if multiplier >= self.spike_threshold and recent_volume >= self.min_volume_for_alert:
            is_significant = multiplier >= self.significant_spike_threshold
            
            spike = VolumeSpike(
                token_address=token_address,
                detected_at=now,
                current_volume_sol=recent_volume,
                average_volume_sol=avg_volume,
                spike_multiplier=multiplier,
                period_minutes=15,
                transaction_count=recent_tx_count,
                is_significant=is_significant,
            )
            
            self._spikes.append(spike)
            return spike
        
        return None
    
    def get_token_volume_trend(
        self,
        token_address: str,
        hours: int = 6,
    ) -> Dict[str, float]:
        """Get volume trend for a token."""
        history = self._volume_history.get(token_address)
        if not history:
            return {"total_volume": 0, "avg_per_hour": 0, "trend": "unknown"}
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        relevant_data = [d for d in history if d.timestamp >= cutoff]
        
        if not relevant_data:
            return {"total_volume": 0, "avg_per_hour": 0, "trend": "unknown"}
        
        total_volume = sum(d.volume_sol for d in relevant_data)
        hours_covered = (relevant_data[-1].timestamp - relevant_data[0].timestamp).total_seconds() / 3600
        hours_covered = max(hours_covered, 0.1)  # Avoid division by zero
        
        # Determine trend
        half_point = len(relevant_data) // 2
        first_half = sum(d.volume_sol for d in relevant_data[:half_point])
        second_half = sum(d.volume_sol for d in relevant_data[half_point:])
        
        if second_half > first_half * 1.5:
            trend = "increasing"
        elif first_half > second_half * 1.5:
            trend = "decreasing"
        else:
            trend = "stable"
        
        return {
            "total_volume": total_volume,
            "avg_per_hour": total_volume / hours_covered,
            "trend": trend,
        }
    
    def format_spike_alert(
        self,
        spike: VolumeSpike,
        token_symbol: str = None,
    ) -> str:
        """Format a volume spike alert."""
        symbol = token_symbol or "???"
        
        if spike.is_significant:
            emoji = "🚀"
            title = "MASSIVE VOLUME SPIKE"
        else:
            emoji = "📈"
            title = "VOLUME SPIKE"
        
        message = f"""
{emoji} <b>{title}</b>

• Token: <b>${symbol}</b>
• Current Volume: <b>{spike.current_volume_sol:.1f} SOL</b> (15 min)
• Average Volume: <b>{spike.average_volume_sol:.1f} SOL</b> (15 min)
• Spike: <b>{spike.spike_multiplier:.1f}x</b> normal
• Transactions: <b>{spike.transaction_count}</b>

<code>{spike.token_address}</code>

<a href="https://dexscreener.com/solana/{spike.token_address}">DexScreener</a> | <a href="https://birdeye.so/token/{spike.token_address}">Birdeye</a>
"""
        return message.strip()
    
    def get_recent_spikes(self, hours: int = 6) -> List[VolumeSpike]:
        """Get volume spikes from the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [s for s in self._spikes if s.detected_at >= cutoff]
    
    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "tracked_tokens": len(self._volume_history),
            "total_spikes": len(self._spikes),
            "significant_spikes": sum(1 for s in self._spikes if s.is_significant),
        }


# Singleton
_volume_detector: VolumeSpikeDetector | None = None


def get_volume_detector() -> VolumeSpikeDetector:
    """Get the singleton volume spike detector."""
    global _volume_detector
    if _volume_detector is None:
        _volume_detector = VolumeSpikeDetector()
    return _volume_detector
