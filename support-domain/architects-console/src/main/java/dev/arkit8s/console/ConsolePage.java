package dev.arkit8s.console;

import io.quarkus.qute.Location;
import io.quarkus.qute.Template;
import io.quarkus.qute.TemplateInstance;
import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import org.eclipse.microprofile.config.inject.ConfigProperty;

/**
 * Serves the Qute-based dashboard inspired by Kubeland.
 */
@Path("/")
public class ConsolePage {

    private final CommandCatalog catalog;
    private final InstallationStatusCatalog installationCatalog;
    private final Template dashboard;
    private final String title;
    private final String description;

    @Inject
    public ConsolePage(
            CommandCatalog catalog,
            InstallationStatusCatalog installationCatalog,
            @Location("dashboard.qute.html") Template dashboard,
            @ConfigProperty(name = "arkit8s.console.title") String title,
            @ConfigProperty(name = "arkit8s.console.description") String description) {
        this.catalog = catalog;
        this.installationCatalog = installationCatalog;
        this.dashboard = dashboard;
        this.title = title;
        this.description = description;
    }

    @GET
    @Produces(MediaType.TEXT_HTML)
    public TemplateInstance get() {
        var snapshot = catalog.snapshot();
        var installation = installationCatalog.snapshot();
        return dashboard.data(
                "commands", snapshot.commands(),
                "generatedAt", snapshot.generatedAt(),
                "installation", installation,
                "title", title,
                "description", description);
    }
}
