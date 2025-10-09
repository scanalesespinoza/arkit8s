package dev.arkit8s.console;

import java.time.Instant;
import java.util.List;

/**
 * Snapshot of the command catalog as exported by arkit8s.py.
 */
public record CommandSnapshot(List<CommandDefinition> commands, Instant generatedAt) {
    public static CommandSnapshot empty() {
        return new CommandSnapshot(List.of(), Instant.EPOCH);
    }
}
