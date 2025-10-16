package dev.arkit8s.console;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

/**
 * REST endpoint exposing the current installation status snapshot.
 */
@Path("/api/installation")
@Produces(MediaType.APPLICATION_JSON)
public class InstallationStatusResource {

    private final InstallationStatusCatalog catalog;

    @Inject
    public InstallationStatusResource(InstallationStatusCatalog catalog) {
        this.catalog = catalog;
    }

    @GET
    public InstallationStatus getStatus() {
        return catalog.snapshot();
    }
}

