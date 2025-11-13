package dev.arkit8s.console;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Event;
import jakarta.enterprise.event.Observes;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import io.quarkus.runtime.StartupEvent;
import io.quarkus.scheduler.Scheduled;

/**
 * Loads CLI commands from the JSON file produced by {@code arkit8s.py sync-web-console}.
 */
@ApplicationScoped
public class CommandCatalog {

    private final ObjectMapper mapper;
    private final Path commandsPath;
    private final Duration refreshInterval;
    private final Event<ConsoleEvent> events;
    private final AtomicReference<CommandSnapshot> snapshot = new AtomicReference<>(CommandSnapshot.empty());
    private volatile FileTime lastLoaded = FileTime.from(Instant.EPOCH);

    @Inject
    public CommandCatalog(
            ObjectMapper mapper,
            @ConfigProperty(name = "arkit8s.console.commands-path") String commandsPath,
            @ConfigProperty(name = "arkit8s.console.refresh-interval") Duration refreshInterval,
            Event<ConsoleEvent> events) {
        this.mapper = mapper;
        this.commandsPath = Path.of(commandsPath);
        this.refreshInterval = refreshInterval;
        this.events = events;
    }

    void onStartup(@Observes StartupEvent event) {
        refresh();
    }

    @Scheduled(every = "1s")
    void watchForChanges() {
        if (refreshInterval.isNegative() || refreshInterval.isZero()) {
            return;
        }
        try {
            var fileTime = Files.exists(commandsPath)
                    ? Files.getLastModifiedTime(commandsPath)
                    : FileTime.from(Instant.EPOCH);
            var threshold = lastLoaded.toInstant().plus(refreshInterval);
            if (fileTime.toInstant().isAfter(threshold)) {
                refresh();
            }
        } catch (IOException e) {
            events.fire(ConsoleEvent.warning("No se pudo vigilar el archivo de comandos: " + e.getMessage()));
        }
    }

    public CommandSnapshot snapshot() {
        var current = snapshot.get();
        events.fire(ConsoleEvent.catalogRead(current));
        return current;
    }

    public Optional<CommandDefinition> findByName(String name) {
        return snapshot().commands().stream()
                .filter(command -> command.name().equalsIgnoreCase(name))
                .findFirst();
    }

    synchronized void refresh() {
        try {
            var updatedSnapshot = readFromFile();
            snapshot.set(updatedSnapshot);
            lastLoaded = Files.exists(commandsPath)
                    ? Files.getLastModifiedTime(commandsPath)
                    : FileTime.from(Instant.now());
            events.fire(ConsoleEvent.catalogReloaded(updatedSnapshot));
        } catch (IOException e) {
            events.fire(ConsoleEvent.warning("No se pudo actualizar el catálogo: " + e.getMessage()));
            throw new UncheckedIOException("Unable to read commands.json", e);
        }
    }

    private CommandSnapshot readFromFile() throws IOException {
        if (!Files.exists(commandsPath)) {
            return new CommandSnapshot(List.of(), Instant.now());
        }

        try (var reader = Files.newBufferedReader(commandsPath)) {
            JsonNode root = mapper.readTree(reader);
            ArrayNode commandsNode = root.has("commands") && root.get("commands").isArray()
                    ? (ArrayNode) root.get("commands")
                    : mapper.createArrayNode();
            List<CommandDefinition> commands = new ArrayList<>();
            commandsNode.forEach(node -> {
                var name = node.path("name").asText();
                var summary = node.path("summary").asText();
                var usage = node.path("usage").asText();
                commands.add(new CommandDefinition(name, summary, usage));
            });
            Instant generatedAt = root.hasNonNull("generated_at")
                    ? Instant.parse(root.get("generated_at").asText())
                    : Instant.now();
            return new CommandSnapshot(List.copyOf(commands), generatedAt);
        }
    }
}
