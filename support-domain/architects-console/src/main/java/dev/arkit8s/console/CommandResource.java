package dev.arkit8s.console;

import jakarta.inject.Inject;
import jakarta.validation.constraints.NotBlank;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

/**
 * REST endpoints for accessing the command catalog.
 */
@Path("/api/commands")
@Produces(MediaType.APPLICATION_JSON)
public class CommandResource {

    private final CommandCatalog catalog;

    @Inject
    public CommandResource(CommandCatalog catalog) {
        this.catalog = catalog;
    }

    @GET
    public CommandSnapshot getCommands() {
        return catalog.snapshot();
    }

    @GET
    @Path("/{name}")
    public CommandDefinition getCommand(@PathParam("name") @NotBlank String name) {
        return catalog.findByName(name)
                .orElseThrow(() -> new NotFoundException("No se encontró el comando " + name));
    }
}
