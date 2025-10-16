package dev.arkit8s.console;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import io.quarkus.runtime.StartupEvent;
import io.quarkus.scheduler.Scheduled;
import jakarta.enterprise.context.ApplicationScoped;
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
import java.util.concurrent.atomic.AtomicReference;

/**
 * Loads the installation status file generated during the architecture bootstrap process.
 */
@ApplicationScoped
public class InstallationStatusCatalog {

    private final ObjectMapper mapper;
    private final Path statusPath;
    private final Duration refreshInterval;
    private final AtomicReference<InstallationStatus> snapshot = new AtomicReference<>(InstallationStatus.empty());
    private volatile FileTime lastLoaded = FileTime.from(Instant.EPOCH);

    @Inject
    public InstallationStatusCatalog(
            ObjectMapper mapper,
            @ConfigProperty(name = "arkit8s.console.installation-status-path") String statusPath,
            @ConfigProperty(name = "arkit8s.console.installation-refresh-interval") Duration refreshInterval) {
        this.mapper = mapper;
        this.statusPath = Path.of(statusPath);
        this.refreshInterval = refreshInterval;
    }

    void onStartup(@Observes StartupEvent event) {
        refresh();
    }

    @Scheduled(every = "2s")
    void watchForChanges() {
        if (refreshInterval.isNegative() || refreshInterval.isZero()) {
            return;
        }
        try {
            var now = Instant.now();
            var nextRefresh = lastLoaded.toInstant().plus(refreshInterval);
            if (now.isBefore(nextRefresh)) {
                return;
            }

            boolean exists = Files.exists(statusPath);
            var fileTime = exists
                    ? Files.getLastModifiedTime(statusPath)
                    : FileTime.from(Instant.EPOCH);

            if (!exists || fileTime.toInstant().isAfter(lastLoaded.toInstant())) {
                refresh();
            }
        } catch (IOException e) {
            snapshot.set(InstallationStatus.empty());
        }
    }

    public InstallationStatus snapshot() {
        return snapshot.get();
    }

    synchronized void refresh() {
        try {
            snapshot.set(readFromFile());
            lastLoaded = Files.exists(statusPath)
                    ? Files.getLastModifiedTime(statusPath)
                    : FileTime.from(Instant.now());
        } catch (IOException e) {
            snapshot.set(InstallationStatus.empty());
            throw new UncheckedIOException("Unable to read installation-status.json", e);
        }
    }

    private InstallationStatus readFromFile() throws IOException {
        if (!Files.exists(statusPath)) {
            return InstallationStatus.empty();
        }

        try (var reader = Files.newBufferedReader(statusPath)) {
            JsonNode root = mapper.readTree(reader);
            String architecture = root.path("architecture").asText("Arquitectura de referencia");
            Instant generatedAt = root.hasNonNull("generated_at")
                    ? Instant.parse(root.get("generated_at").asText())
                    : Instant.now();
            String overallStatus = root.path("status").asText("DESCONOCIDO");
            int progress = root.path("progress").asInt(-1);
            String detail = root.path("detail").asText("");

            List<InstallationPhase> phases = new ArrayList<>();
            ArrayNode phasesNode = root.has("phases") && root.get("phases").isArray()
                    ? (ArrayNode) root.get("phases")
                    : mapper.createArrayNode();
            phasesNode.forEach(node -> phases.add(new InstallationPhase(
                    node.path("name").asText(),
                    node.path("status").asText("DESCONOCIDO"),
                    node.path("detail").asText(""),
                    parseInstant(node.get("started_at")),
                    parseInstant(node.get("completed_at")))));

            List<InstalledResource> resources = new ArrayList<>();
            ArrayNode resourcesNode = root.has("resources") && root.get("resources").isArray()
                    ? (ArrayNode) root.get("resources")
                    : mapper.createArrayNode();
            resourcesNode.forEach(node -> resources.add(new InstalledResource(
                    node.path("kind").asText(),
                    node.path("name").asText(),
                    node.path("namespace").asText("default"),
                    node.path("status").asText("DESCONOCIDO"),
                    node.path("message").asText(""),
                    node.path("age").asText("-"))));

            return new InstallationStatus(
                    architecture,
                    generatedAt,
                    overallStatus,
                    progress,
                    detail,
                    List.copyOf(phases),
                    List.copyOf(resources));
        }
    }

    private Instant parseInstant(JsonNode node) {
        if (node == null || node.isNull() || node.asText().isBlank()) {
            return null;
        }
        return Instant.parse(node.asText());
    }
}

