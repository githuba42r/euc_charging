"""Charge time estimator for EUCs with Li-ion charge curve modeling."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from time import time
from typing import Optional

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChargeEstimates:
    """Estimated times to reach charge levels."""
    time_to_80: int | None = None   # Minutes
    time_to_90: int | None = None
    time_to_95: int | None = None
    time_to_100: int | None = None
    charge_rate_pct: float = 0.0     # Percent per minute (current rate)
    averaging_window: str = "unknown"  # Which time window was used for calculation
    
    def format_time(self, minutes: int | None) -> str | None:
        """Format time in minutes as H:MM hr format.
        
        Args:
            minutes: Time in minutes
            
        Returns:
            Formatted string like "1:42 hr", "--" for < 1 minute, or None if minutes is None
        """
        if minutes is None:
            return None
        
        # Display "--" for values less than 1 minute (target reached or nearly there)
        if minutes < 1:
            return "--"
        
        if minutes < 60:
            return f"0:{minutes:02d} hr"
        
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}:{mins:02d} hr"
    
    @property
    def time_to_80_formatted(self) -> str | None:
        """Get formatted time to 80%."""
        return self.format_time(self.time_to_80)
    
    @property
    def time_to_90_formatted(self) -> str | None:
        """Get formatted time to 90%."""
        return self.format_time(self.time_to_90)
    
    @property
    def time_to_95_formatted(self) -> str | None:
        """Get formatted time to 95%."""
        return self.format_time(self.time_to_95)
    
    @property
    def time_to_100_formatted(self) -> str | None:
        """Get formatted time to 100%."""
        return self.format_time(self.time_to_100)


class LiIonChargeModel:
    """Model for Li-ion battery charging curve.
    
    Li-ion batteries follow a CC-CV (Constant Current - Constant Voltage) charging profile:
    - CC Phase (0-80%): Nearly linear charging at constant current
    - Transition (80-90%): Current starts tapering as voltage approaches max
    - CV Phase (90-100%): Constant voltage, current tapers exponentially
    
    The rate reduction factors are based on typical Li-ion charging characteristics.
    """
    
    # Charge curve breakpoints and relative speed factors
    # These represent how much slower charging is in each region compared to CC phase
    CURVE_POINTS = [
        (0, 1.0),      # 0-80%: Full speed (CC phase)
        (80, 1.0),     # 80%: Still full speed
        (85, 0.85),    # 85%: Starting to slow down
        (90, 0.65),    # 90%: Significant slowdown (CV phase begins)
        (93, 0.50),    # 93%: Half speed
        (95, 0.35),    # 95%: Much slower
        (97, 0.20),    # 97%: Very slow
        (99, 0.10),    # 99%: Crawling
        (100, 0.05),   # 100%: Nearly stopped
    ]
    
    @classmethod
    def get_speed_factor(cls, soc: float) -> float:
        """Get the relative charging speed factor at a given state of charge.
        
        Args:
            soc: State of charge (0-100%)
            
        Returns:
            Speed factor (1.0 = full speed, 0.5 = half speed, etc.)
        """
        # Find the two points that bracket the current SOC
        for i in range(len(cls.CURVE_POINTS) - 1):
            soc1, factor1 = cls.CURVE_POINTS[i]
            soc2, factor2 = cls.CURVE_POINTS[i + 1]
            
            if soc1 <= soc <= soc2:
                # Linear interpolation between the two points
                if soc2 == soc1:
                    return factor1
                ratio = (soc - soc1) / (soc2 - soc1)
                return factor1 + (factor2 - factor1) * ratio
        
        # If beyond 100%, return the slowest factor
        if soc >= 100:
            return cls.CURVE_POINTS[-1][1]
        # If below 0%, return full speed
        return cls.CURVE_POINTS[0][1]
    
    @classmethod
    def estimate_time_to_target(cls, current_soc: float, target_soc: float, 
                                 current_rate_pct_min: float) -> Optional[int]:
        """Estimate time to reach target SOC using the charge curve model.
        
        Args:
            current_soc: Current state of charge (0-100%)
            target_soc: Target state of charge (0-100%)
            current_rate_pct_min: Current measured charge rate in %/min
            
        Returns:
            Estimated minutes to reach target, or None if not charging
        """
        if current_rate_pct_min <= 0 or current_soc >= target_soc:
            return None if current_soc < target_soc else 0
        
        # Get the current speed factor to normalize the rate
        current_factor = cls.get_speed_factor(current_soc)
        if current_factor <= 0:
            return None
        
        # Estimate the "base" charging rate (what it would be in CC phase)
        base_rate = current_rate_pct_min / current_factor
        
        # Integrate over the charge curve from current to target
        # We'll use small steps to account for the non-linear curve
        step_size = 0.5  # 0.5% steps for reasonable accuracy
        total_time = 0.0
        soc = current_soc
        
        while soc < target_soc:
            next_soc = min(soc + step_size, target_soc)
            mid_soc = (soc + next_soc) / 2
            
            # Get speed factor at the midpoint
            factor = cls.get_speed_factor(mid_soc)
            
            # Calculate time for this segment
            # time = distance / speed = (percent_to_charge) / (rate * factor)
            segment_percent = next_soc - soc
            if factor > 0:
                segment_rate = base_rate * factor
                segment_time = segment_percent / segment_rate
                total_time += segment_time
            
            soc = next_soc
        
        return int(round(total_time))


class ChargeTracker:
    """Tracks charging progress and estimates completion times using Li-ion charge curves.
    
    Uses adaptive multi-timeframe averaging:
    - 1 minute window: Quick initial estimate (after 1 minute of data)
    - 5 minute window: Better accuracy (after 5 minutes of data)
    - 30 minute window: High accuracy (after 30 minutes of data)
    - 1 hour window: Maximum accuracy (after 1 hour of data)
    """

    def __init__(self, max_samples: int = 3600, update_interval: int = 45, smoothing_alpha: float = 0.1) -> None:
        """Initialize the tracker.
        
        Args:
            max_samples: Maximum number of samples to keep (default 3600 = 1 hour at 1 sample/sec)
            update_interval: Seconds between estimate updates to prevent jumping values (default 45)
            smoothing_alpha: Exponential smoothing factor (0-1). Lower = smoother, higher = more responsive (default 0.3)
        """
        # Store tuples of (timestamp, battery_percent, voltage)
        # Keep up to 1 hour of history for long-term averaging
        self._history: deque[tuple[float, float, float]] = deque(maxlen=max_samples)
        self._last_estimate: ChargeEstimates | None = None
        self._last_update_time: float = 0.0  # When we last updated the estimate
        self._update_interval: int = update_interval  # Seconds between updates
        self._smoothing_alpha: float = smoothing_alpha  # EMA smoothing factor
        self._smoothed_rate: float | None = None  # Exponentially smoothed rate
        
        # Adaptive time windows (in seconds)
        # We'll use the longest available window that has enough data
        self._time_windows = [
            (60, "1min"),      # 1 minute - quick initial estimate
            (300, "5min"),     # 5 minutes - better accuracy
            (1800, "30min"),   # 30 minutes - high accuracy
            (3600, "1hour"),   # 1 hour - maximum accuracy
        ]

    def update(self, battery_percent: float, is_charging: bool, 
               voltage: float = 0.0) -> ChargeEstimates:
        """Update tracker with new data and return estimates.
        
        Args:
            battery_percent: Current battery percentage (0-100)
            is_charging: Whether the device is currently charging
            voltage: Current battery voltage (for future use)
        """
        now = time()
        
        if not is_charging:
            # Reset everything when not charging
            if self._history:  # Only log if we were tracking
                _LOGGER.info("Charging stopped (is_charging=False), clearing history")
            self._history.clear()
            self._last_estimate = None
            self._last_update_time = 0.0
            self._smoothed_rate = None
            return ChargeEstimates()

        # Add new sample
        is_first_sample = len(self._history) == 0
        self._history.append((now, battery_percent, voltage))
        
        if is_first_sample:
            _LOGGER.info(
                "Charging started at %.1f%%. Collecting data for charge time estimates...",
                battery_percent
            )
        
        # Special case: If battery is at or very near 100%, return estimates immediately
        # No need to wait for data collection or calculate rates
        if battery_percent >= 99.5:
            estimates = ChargeEstimates(
                charge_rate_pct=0.0,
                averaging_window="instant",
            )
            estimates.time_to_80 = 0
            estimates.time_to_90 = 0
            estimates.time_to_95 = 0
            estimates.time_to_100 = 0
            self._last_estimate = estimates
            _LOGGER.debug(
                "Battery at %.1f%%, returning immediate estimates (all zeros)",
                battery_percent
            )
            return estimates
        
        # Check if enough time has passed since last update to prevent jumping values
        # Always calculate on first estimate or when window would change
        time_since_last_update = now - self._last_update_time
        should_update = (
            self._last_estimate is None or  # First estimate
            time_since_last_update >= self._update_interval  # Enough time passed
        )
        
        if not should_update:
            # Return the cached estimate to prevent jumping
            # If we have a cached estimate, return it; otherwise return empty estimate
            if self._last_estimate:
                return self._last_estimate
            # This shouldn't happen (should_update would be True if _last_estimate is None)
            # but handle it just in case
            return ChargeEstimates()
        
        # Calculate the total time span of our data
        total_time_span = now - self._history[0][0]
        
        # Determine which time window to use based on available data
        # Use the largest window that we have enough data for
        selected_window_seconds = None
        selected_window_name = "unknown"  # Default value
        
        for window_seconds, window_name in self._time_windows:
            if total_time_span >= window_seconds:
                selected_window_seconds = window_seconds
                selected_window_name = window_name
        
        # Check if window changed - force update if so
        window_changed = (self._last_estimate is not None and 
                         self._last_estimate.averaging_window != selected_window_name)
        
        # If we don't have even 1 minute of data yet, try with what we have
        # but require at least 30 seconds to avoid noise
        if selected_window_seconds is None:
            if total_time_span >= 30:
                selected_window_seconds = total_time_span
                selected_window_name = f"{int(total_time_span)}sec"
            else:
                # Not enough data yet
                _LOGGER.debug(
                    "Collecting initial data: %.1f/30 seconds elapsed",
                    total_time_span
                )
                return self._last_estimate or ChargeEstimates()
        
        # Calculate rate using data from the selected time window
        raw_rate_pct_min = self._calculate_rate_for_window(selected_window_seconds)
        
        # If rate is negative or too small, return previous estimates or special case
        if raw_rate_pct_min is None or raw_rate_pct_min <= 0.001:
            # Only warn if battery is not nearly full (when low/negative rates are expected)
            if raw_rate_pct_min is not None and raw_rate_pct_min <= 0.001 and battery_percent < 99.0:
                _LOGGER.warning(
                    "Charge rate too low or negative: %.4f %%/min (SOC: %.1f%%, window: %s, time span: %.1f sec)",
                    raw_rate_pct_min, battery_percent, selected_window_name, total_time_span
                )
            elif raw_rate_pct_min is not None and battery_percent >= 99.0:
                # Battery is nearly full, this is expected behavior in CV phase
                _LOGGER.debug(
                    "Battery nearly full (%.1f%%), charge rate very low: %.4f %%/min - this is normal",
                    battery_percent, raw_rate_pct_min
                )
            
            # Safety net: If battery reached 100% during charging, return zeros
            # This shouldn't normally be reached as we check at the start
            if battery_percent >= 99.5:
                estimates = ChargeEstimates(
                    charge_rate_pct=0.0,
                    averaging_window=selected_window_name,
                )
                estimates.time_to_80 = 0
                estimates.time_to_90 = 0
                estimates.time_to_95 = 0
                estimates.time_to_100 = 0
                self._last_estimate = estimates
                _LOGGER.debug(
                    "Battery at %.1f%%, setting all time estimates to 0",
                    battery_percent
                )
                return estimates
            
            return self._last_estimate or ChargeEstimates()

        # Apply exponential smoothing to the rate to prevent rapid changes
        # Formula: smoothed = alpha * new_value + (1 - alpha) * old_value
        # Lower alpha = more smoothing, higher alpha = more responsive
        if self._smoothed_rate is None or window_changed:
            # First estimate or window changed - use raw rate
            rate_pct_min = raw_rate_pct_min
            self._smoothed_rate = raw_rate_pct_min
        else:
            # Apply exponential moving average
            rate_pct_min = (
                self._smoothing_alpha * raw_rate_pct_min + 
                (1 - self._smoothing_alpha) * self._smoothed_rate
            )
            self._smoothed_rate = rate_pct_min

        # Create estimates using the Li-ion charge model
        estimates = ChargeEstimates(
            charge_rate_pct=round(rate_pct_min, 3),
            averaging_window=selected_window_name,
        )
        
        current_soc = battery_percent
        
        # Calculate time to each target using the charge curve model
        # Return 0 if already at or above target, otherwise calculate
        estimates.time_to_80 = (
            LiIonChargeModel.estimate_time_to_target(current_soc, 80.0, rate_pct_min)
            if current_soc < 80.0 else 0
        )
        estimates.time_to_90 = (
            LiIonChargeModel.estimate_time_to_target(current_soc, 90.0, rate_pct_min)
            if current_soc < 90.0 else 0
        )
        estimates.time_to_95 = (
            LiIonChargeModel.estimate_time_to_target(current_soc, 95.0, rate_pct_min)
            if current_soc < 95.0 else 0
        )
        estimates.time_to_100 = (
            LiIonChargeModel.estimate_time_to_target(current_soc, 100.0, rate_pct_min)
            if current_soc < 100.0 else 0
        )
        
        # Log when we first get valid estimates, when window changes, or periodically
        is_first_estimate = self._last_estimate is None or self._last_estimate.charge_rate_pct == 0
        
        # Log raw vs smoothed rate for debugging (only occasionally)
        if is_first_estimate:
            _LOGGER.info(
                "Charge estimates now available! SOC=%.1f%%, Rate=%.3f%%/min (raw=%.3f, window: %s), "
                "Time to [80%%=%s, 90%%=%s, 95%%=%s, 100%%=%s]",
                current_soc, rate_pct_min, raw_rate_pct_min, selected_window_name,
                estimates.time_to_80_formatted, estimates.time_to_90_formatted,
                estimates.time_to_95_formatted, estimates.time_to_100_formatted
            )
        elif window_changed:
            _LOGGER.info(
                "Charge estimate window upgraded to %s. SOC=%.1f%%, Rate=%.3f%%/min (raw=%.3f), "
                "Time to [80%%=%s, 90%%=%s, 95%%=%s, 100%%=%s]",
                selected_window_name, current_soc, rate_pct_min, raw_rate_pct_min,
                estimates.time_to_80_formatted, estimates.time_to_90_formatted,
                estimates.time_to_95_formatted, estimates.time_to_100_formatted
            )
        else:
            # Regular update (every update_interval seconds)
            # Show difference between raw and smoothed to see how much smoothing is happening
            rate_diff = abs(raw_rate_pct_min - rate_pct_min)
            _LOGGER.debug(
                "Charge estimates updated: SOC=%.1f%%, Rate=%.3f%%/min (raw=%.3f, diff=%.3f, window: %s), "
                "Time to [80%%=%s, 90%%=%s, 95%%=%s, 100%%=%s]",
                current_soc, rate_pct_min, raw_rate_pct_min, rate_diff, selected_window_name,
                estimates.time_to_80_formatted, estimates.time_to_90_formatted,
                estimates.time_to_95_formatted, estimates.time_to_100_formatted
            )
        
        # Save the estimate and update time
        self._last_estimate = estimates
        self._last_update_time = now
        
        return estimates
    
    def _calculate_rate_for_window(self, window_seconds: float) -> Optional[float]:
        """Calculate charge rate using data from a specific time window.
        
        Args:
            window_seconds: Size of the time window in seconds
            
        Returns:
            Charge rate in %/min, or None if unable to calculate
        """
        if not self._history or len(self._history) < 2:
            return None
        
        now = self._history[-1][0]
        cutoff_time = now - window_seconds
        
        # Find the samples within the window
        window_samples = []
        for timestamp, soc, voltage in self._history:
            if timestamp >= cutoff_time:
                window_samples.append((timestamp, soc, voltage))
        
        if len(window_samples) < 2:
            return None
        
        # Use linear regression for better noise resistance
        # Convert timestamps to minutes from start of window
        start_time = window_samples[0][0]
        times = [(t - start_time) / 60.0 for t, _, _ in window_samples]
        socs = [soc for _, soc, _ in window_samples]
        
        # Simple linear regression for % per minute
        n = len(times)
        sum_t = sum(times)
        sum_soc = sum(socs)
        sum_t_soc = sum(t * soc for t, soc in zip(times, socs))
        sum_t_sq = sum(t * t for t in times)
        
        denominator = n * sum_t_sq - sum_t * sum_t
        if denominator == 0:
            return None
        
        # Slope = rate in %/min
        rate_pct_min = (n * sum_t_soc - sum_t * sum_soc) / denominator
        
        return rate_pct_min
