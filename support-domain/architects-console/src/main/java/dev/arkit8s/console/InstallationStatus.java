package dev.arkit8s.console;

import java.time.Instant;
import java.util.List;

/**
 * Aggregated view of the installation progress for the reference architecture.
 */
public record InstallationStatus(
        String architecture,
        Instant generatedAt,
        String status,
        int progress,
        String detail,
        List<InstallationPhase> phases,
        List<InstalledResource> resources) {

    public static InstallationStatus empty() {
        return new InstallationStatus(
                "Arquitectura de referencia",
                Instant.now(),
                "SIN_DATOS",
                -1,
                "Aún no se registran eventos de instalación.",
                List.of(),
                List.of());
    }
}

