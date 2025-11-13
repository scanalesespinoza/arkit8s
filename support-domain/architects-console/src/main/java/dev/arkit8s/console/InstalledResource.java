package dev.arkit8s.console;

/**
 * Describes a Kubernetes resource that is provisioned as part of the reference architecture.
 */
public record InstalledResource(
        String kind,
        String name,
        String namespace,
        String status,
        String message,
        String age) {
}

