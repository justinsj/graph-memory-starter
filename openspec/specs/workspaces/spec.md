# workspaces Specification

## Purpose
Teams kept apart, on SQLite or Postgres, and callers known by their keys and tokens.

## Requirements
### Requirement: Workspaces kept apart
The service SHALL keep each workspace's rows apart, and on Postgres MUST enforce it with row-level security under a role that is not a superuser.

#### Scenario: One workspace never sees another
- **WHEN** one workspace asks for another's sources, projects or change requests
- **THEN** it finds none of them

#### Scenario: Every table but two carries its workspace
- **WHEN** the schema is read
- **THEN** every table but workspaces and users has a workspace_id

#### Scenario: Row security hides other workspaces even without a filter
- **WHEN** a transaction for one workspace reads a table without a filter
- **THEN** it sees only that workspace's rows

#### Scenario: Row security refuses writes for another workspace
- **WHEN** a transaction for one workspace writes a row for another
- **THEN** the database refuses it

#### Scenario: The app role is not a superuser
- **WHEN** the service connects to Postgres
- **THEN** its role is kl_app, which is not a superuser

#### Scenario: Postgres and sqlite give the same context
- **WHEN** the same questions are asked on both backends
- **THEN** the answers are the same

#### Scenario: The answer is the one recall gives in process
- **WHEN** the refund question is asked
- **THEN** the answer is in-process recall's

### Requirement: Callers and what they may do
The service SHALL know people by OIDC tokens or personal keys, systems by service account keys and agents by run tokens, and SHALL allow each only its role's or key's scopes.

#### Scenario: A person signs in with the issuers token once an admin has added them
- **WHEN** a person with a valid token is not a member, and then is added
- **THEN** they are refused, and then signed in with their role

#### Scenario: A token for another audience or expired or forged is refused
- **WHEN** a token is for another audience, expired, from another issuer or signed by another key
- **THEN** it is refused with 401

#### Scenario: A person says which workspace
- **WHEN** a person's token comes without KL-Workspace
- **THEN** it is refused, saying so

#### Scenario: Roles decide what a person may do
- **WHEN** a viewer proposes a project or sends a file
- **THEN** it is refused

#### Scenario: Only the root key creates workspaces
- **WHEN** an admin's key and the root key each create a workspace
- **THEN** only the root key's succeeds

#### Scenario: A revoked key stops working
- **WHEN** a key is revoked
- **THEN** it is refused at once

#### Scenario: Errors are problems
- **WHEN** a call fails
- **THEN** the answer is application/problem+json with type, title, status and detail
