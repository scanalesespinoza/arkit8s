package dev.arkit8s.console;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import io.quarkus.test.junit.QuarkusTest;
import io.restassured.RestAssured;
import org.junit.jupiter.api.Test;

@QuarkusTest
class InstallationStatusResourceTest {

    @Test
    void installationStatusSnapshotIsExposed() {
        var response = RestAssured.get("/api/installation")
                .then()
                .statusCode(200)
                .extract()
                .as(InstallationStatus.class);

        assertEquals("Arkit8s Reference", response.architecture());
        assertEquals("APPLYING", response.status());
        assertFalse(response.phases().isEmpty());
        assertFalse(response.resources().isEmpty());
    }
}
