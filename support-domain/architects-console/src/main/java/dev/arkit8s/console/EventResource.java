package dev.arkit8s.console;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import java.util.List;

/**
 * Exposes the recent event flow so the UI can render activity without polling the logs.
 */
@Path("/api/events")
@Produces(MediaType.APPLICATION_JSON)
public class EventResource {

    private final ConsoleEventLog log;

    @Inject
    public EventResource(ConsoleEventLog log) {
        this.log = log;
    }

    @GET
    public List<ConsoleEvent> getEvents() {
        return log.recentEvents();
    }
}
