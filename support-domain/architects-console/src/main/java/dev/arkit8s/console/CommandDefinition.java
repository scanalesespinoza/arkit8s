package dev.arkit8s.console;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * Immutable representation of a CLI command exposed by the web console.
 */
public record CommandDefinition(
        @NotBlank String name,
        @NotBlank @Size(max = 512) String summary,
        @NotBlank @Size(max = 512) String usage) {

    public String canonicalCommand() {
        return usage().replace("usage:", "").trim();
    }
}
