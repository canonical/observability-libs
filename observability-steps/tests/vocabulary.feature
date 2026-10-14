Feature: Vocabulary
  Every sentence the package defines, as a suite would write it.

  Scenario: TLS
    Given a certificates provider is deployed
    And the "my-app" application is integrated with the certificates provider
    When the "my-app" application is integrated with the certificates provider
    Then the "my-app" application serves HTTPS on port 8080

  Scenario: Logs
    Given Loki is deployed
    And the "my-app" application is integrated with Loki
    When the "my-app" application is integrated with Loki
    Then Loki has logs from the "my-app" application
