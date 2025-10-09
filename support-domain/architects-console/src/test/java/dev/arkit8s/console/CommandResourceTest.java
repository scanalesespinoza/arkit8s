package dev.arkit8s.console;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import io.quarkus.test.junit.QuarkusTest;
import io.restassured.RestAssured;
import org.junit.jupiter.api.Test;

@QuarkusTest
class CommandResourceTest {
    @Test
    void listCommands() {
        var response = RestAssured.get("/api/commands")
                .then()
                .statusCode(200)
                .extract()
                .as(CommandSnapshot.class);

        assertEquals(2, response.commands().size());
        assertEquals("install", response.commands().get(0).name());
        assertFalse(response.commands().isEmpty());
    }
}
