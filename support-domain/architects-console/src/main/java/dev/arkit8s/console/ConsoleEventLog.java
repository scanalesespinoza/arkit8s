package dev.arkit8s.console;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;

/**
 * Keeps the latest console events in memory so they can be exposed via REST.
 */
@ApplicationScoped
public class ConsoleEventLog {

    private static final int MAX_EVENTS = 64;
    private final Deque<ConsoleEvent> events = new ArrayDeque<>();

    void onEvent(@Observes ConsoleEvent event) {
        synchronized (events) {
            events.addFirst(event);
            while (events.size() > MAX_EVENTS) {
                events.removeLast();
            }
        }
    }

    public List<ConsoleEvent> recentEvents() {
        synchronized (events) {
            return List.copyOf(events);
        }
    }
}
