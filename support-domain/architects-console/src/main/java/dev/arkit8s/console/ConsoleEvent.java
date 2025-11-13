package dev.arkit8s.console;

import java.time.Instant;

/**
 * Event emitted whenever the command catalog changes or is read.
 */
public record ConsoleEvent(String type, Instant at, int commandCount, String detail) {
    public static ConsoleEvent catalogReloaded(CommandSnapshot snapshot) {
        var detail = "Catálogo sincronizado con " + snapshot.commands().size() + " comandos";
        return new ConsoleEvent("CATALOG_RELOADED", Instant.now(), snapshot.commands().size(), detail);
    }

    public static ConsoleEvent catalogRead(CommandSnapshot snapshot) {
        return new ConsoleEvent("CATALOG_READ", Instant.now(), snapshot.commands().size(), "Lectura del catálogo");
    }

    public static ConsoleEvent warning(String message) {
        return new ConsoleEvent("WARNING", Instant.now(), 0, message);
    }
}
