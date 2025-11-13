package dev.arkit8s.console;

import java.time.Instant;

/**
 * Represents a phase within the reference architecture installation workflow.
 */
public record InstallationPhase(
        String name,
        String status,
        String detail,
        Instant startedAt,
        Instant completedAt) {
}

