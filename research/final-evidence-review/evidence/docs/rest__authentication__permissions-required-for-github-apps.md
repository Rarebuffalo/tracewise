# Permissions required for GitHub Apps

For each permission granted to a GitHub App, these are the REST API endpoints that the app can use.

## About GitHub App permissions

GitHub Apps are created with a set of permissions. Permissions define what resources the GitHub App can access via the API. For more information, see [Choosing permissions for a GitHub App](/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).

To help you choose the correct permissions, you will receive the `X-Accepted-GitHub-Permissions` header in the REST API response. The header will tell you what permissions are required in order to access the endpoint. For more information, see [Troubleshooting the REST API](/en/rest/using-the-rest-api/troubleshooting-the-rest-api#resource-not-accessible).

These permissions are required to access private resources. Some endpoints can also be used to access public resources without these permissions. To see whether an endpoint can access public resources without a permission, see the documentation for that endpoint.

Some endpoints require more than one permission. Other endpoints work with any one permission from a set of permissions. In these cases, the "Additional permissions" column will include a checkmark. For full details about the permissions that are required to use the endpoint, see the documentation for that endpoint.

**Token types:** UAT = user access token, IAT = installation access token

## Enterprise permissions for "Enterprise Copilot metrics"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /enterprises/{enterprise}/copilot/metrics/reports/enterprise-1-day` | read | UAT, IAT | ✗ |
| `GET /enterprises/{enterprise}/copilot/metrics/reports/enterprise-28-day/latest` | read | UAT, IAT | ✗ |
| `GET /enterprises/{enterprise}/copilot/metrics/reports/repos-1-day` | read | UAT, IAT | ✗ |
| `GET /enterprises/{enterprise}/copilot/metrics/reports/user-teams-1-day` | read | UAT, IAT | ✗ |
| `GET /enterprises/{enterprise}/copilot/metrics/reports/users-1-day` | read | UAT, IAT | ✗ |
| `GET /enterprises/{enterprise}/copilot/metrics/reports/users-28-day/latest` | read | UAT, IAT | ✗ |

## Organization permissions for "API Insights"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /orgs/{org}/insights/api/route-stats/{actor_type}/{actor_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/subject-stats` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/summary-stats` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/summary-stats/users/{user_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/summary-stats/{actor_type}/{actor_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/time-stats` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/time-stats/users/{user_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/time-stats/{actor_type}/{actor_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/insights/api/user-stats/{user_id}` | read | UAT, IAT | ✗ |

## Organization permissions for "Administration"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /organizations/{org}/actions/cache/retention-limit` | write | UAT, IAT | ✗ |
| `PUT /organizations/{org}/actions/cache/storage-limit` | write | UAT, IAT | ✗ |
| `POST /organizations/{org}/settings/billing/budgets` | write | UAT, IAT | ✗ |
| `PATCH /organizations/{org}/settings/billing/budgets/{budget_id}` | write | UAT, IAT | ✗ |
| `DELETE /organizations/{org}/settings/billing/budgets/{budget_id}` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/actions/hosted-runners` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/actions/hosted-runners/{hosted_runner_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/hosted-runners/{hosted_runner_id}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/actions/oidc/customization/properties/repo` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/oidc/customization/properties/repo/{custom_property_name}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/oidc/customization/sub` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/artifact-and-log-retention` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/fork-pr-contributor-approval` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/fork-pr-workflows-private-repos` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/actions/permissions/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `PUT /orgs/{org}/actions/permissions/selected-actions` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/self-hosted-runners` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/self-hosted-runners/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/permissions/self-hosted-runners/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/actions/permissions/self-hosted-runners/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `PUT /orgs/{org}/actions/permissions/workflow` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/policies` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/actions/policies` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/policies/{policy_id}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/policies/{policy_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/policies/{policy_id}` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/code-scanning/ai-scan` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/code-security/configurations` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/code-security/configurations/detach` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/code-security/configurations/{configuration_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/code-security/configurations/{configuration_id}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/code-security/configurations/{configuration_id}/attach` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/code-security/configurations/{configuration_id}/defaults` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/copilot/billing/selected_teams` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/copilot/billing/selected_teams` | write | UAT, IAT | ✓ |
| `POST /orgs/{org}/copilot/billing/selected_users` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/copilot/billing/selected_users` | write | UAT, IAT | ✓ |
| `PATCH /orgs/{org}/dependabot/repository-access` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/dependabot/repository-access/default-level` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/interaction-limits` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/interaction-limits` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/interaction-limits/pulls/creation-cap` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/interaction-limits/pulls/creation-cap` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/rulesets` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/rulesets` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/rulesets/rule-suites` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/rulesets/rule-suites/{rule_suite_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/rulesets/{ruleset_id}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/rulesets/{ruleset_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/rulesets/{ruleset_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/rulesets/{ruleset_id}/history` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/rulesets/{ruleset_id}/history/{version_id}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/secret-scanning/custom-patterns` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/secret-scanning/custom-patterns` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/secret-scanning/custom-patterns/{pattern_id}` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/secret-scanning/pattern-configurations` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/security-managers/teams/{team_slug}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/security-managers/teams/{team_slug}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/settings/immutable-releases` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/settings/immutable-releases/repositories` | write | UAT, IAT | ✓ |
| `PUT /orgs/{org}/settings/immutable-releases/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/settings/immutable-releases/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `POST /orgs/{org}/{security_product}/{enablement}` | write | UAT, IAT | ✗ |
| `GET /organizations/{org}/actions/cache/retention-limit` | read | UAT, IAT | ✗ |
| `GET /organizations/{org}/actions/cache/storage-limit` | read | UAT, IAT | ✗ |
| `GET /organizations/{org}/settings/billing/ai_credit/usage` | read | UAT, IAT | ✗ |
| `GET /organizations/{org}/settings/billing/budgets` | read | UAT, IAT | ✗ |
| `GET /organizations/{org}/settings/billing/budgets/{budget_id}` | read | UAT, IAT | ✗ |
| `GET /organizations/{org}/settings/billing/premium_request/usage` | read | UAT, IAT | ✗ |
| `GET /organizations/{org}/settings/billing/usage` | read | UAT, IAT | ✗ |
| `GET /organizations/{org}/settings/billing/usage/summary` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/cache/usage` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/cache/usage-by-repository` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/images/github-owned` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/images/partner` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/limits` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/machine-sizes` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/platforms` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/{hosted_runner_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/oidc/customization/properties/repo` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/oidc/customization/sub` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/artifact-and-log-retention` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/fork-pr-contributor-approval` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/fork-pr-workflows-private-repos` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/repositories` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/selected-actions` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/self-hosted-runners` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/self-hosted-runners/repositories` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/permissions/workflow` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/code-scanning/ai-scan` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/code-security/configurations` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/code-security/configurations/defaults` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/code-security/configurations/{configuration_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/code-security/configurations/{configuration_id}/repositories` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/billing` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/copilot/billing/seats` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/dependabot/repository-access` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/installations` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/interaction-limits` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/members/{username}/copilot` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/secret-scanning/custom-patterns` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/secret-scanning/pattern-configurations` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/security-managers` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/settings/immutable-releases` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/settings/immutable-releases/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Agent secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/agents/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/agents/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/agents/secrets/{secret_name}/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/agents/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/agents/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/agents/secrets` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/agents/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/agents/secrets/{secret_name}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/agents/secrets/{secret_name}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Agent variables"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/agents/variables` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/agents/variables/{name}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/agents/variables/{name}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/agents/variables/{name}/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/agents/variables/{name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/agents/variables/{name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/agents/variables` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/agents/variables/{name}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/agents/variables/{name}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Blocking users"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/blocks/{username}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/blocks/{username}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/blocks` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/blocks/{username}` | read | UAT, IAT | ✗ |

## Organization permissions for "Campaigns"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/campaigns` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/campaigns/{campaign_number}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/campaigns/{campaign_number}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/campaigns` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/campaigns/{campaign_number}` | read | UAT, IAT | ✗ |

## Organization permissions for "Copilot Spaces"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/copilot-spaces` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/copilot-spaces/{space_number}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/copilot-spaces/{space_number}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/copilot-spaces/{space_number}/resources` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/copilot-spaces/{space_number}/resources/{space_resource_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/copilot-spaces/{space_number}/resources/{space_resource_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot-spaces` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot-spaces/{space_number}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot-spaces/{space_number}/resources` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot-spaces/{space_number}/resources/{space_resource_id}` | read | UAT, IAT | ✗ |

## Organization permissions for "Copilot agent settings"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/copilot/coding-agent/permissions` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/copilot/coding-agent/permissions/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/copilot/coding-agent/permissions/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/copilot/coding-agent/permissions/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/copilot/coding-agent/permissions` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/coding-agent/permissions/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Copilot content exclusion"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/copilot/content_exclusion` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/content_exclusion` | read | UAT, IAT | ✗ |

## Organization permissions for "Custom organization roles"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /orgs/{org}/organization-roles` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/organization-roles/{role_id}` | read | UAT, IAT | ✗ |

## Organization permissions for "Custom properties"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /orgs/{org}/properties/schema` | admin | UAT, IAT | ✗ |
| `PUT /orgs/{org}/properties/schema/{custom_property_name}` | admin | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/properties/schema/{custom_property_name}` | admin | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/properties/values` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/properties/schema` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/properties/schema/{custom_property_name}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/properties/values` | read | UAT, IAT | ✗ |

## Organization permissions for "Events"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /users/{username}/events/orgs/{org}` | read | UAT | ✗ |

## Organization permissions for "External custom properties for repositories"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /orgs/{org}/properties/installations` | admin | UAT, IAT | ✗ |
| `POST /orgs/{org}/properties/installations` | admin | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/properties/installations/values` | write | IAT | ✗ |
| `PATCH /orgs/{org}/properties/installations/values/{property_name}` | write | IAT | ✗ |
| `DELETE /orgs/{org}/properties/installations/values/{property_name}` | write | IAT | ✗ |
| `GET /orgs/{org}/properties/installations/schema` | read | IAT | ✗ |

## Organization permissions for "GitHub Copilot Business"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/copilot-spaces/{space_number}/collaborators` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/copilot-spaces/{space_number}/collaborators/{actor_type}/{actor_identifier}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/copilot-spaces/{space_number}/collaborators/{actor_type}/{actor_identifier}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/copilot/billing/selected_teams` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/copilot/billing/selected_teams` | write | UAT, IAT | ✓ |
| `POST /orgs/{org}/copilot/billing/selected_users` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/copilot/billing/selected_users` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/copilot-spaces/{space_number}/collaborators` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/billing` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/copilot/billing/seats` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/members/{username}/copilot` | read | UAT, IAT | ✓ |

## Organization permissions for "Hosted runner custom images"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `DELETE /orgs/{org}/actions/hosted-runners/images/custom/{image_definition_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/hosted-runners/images/custom/{image_definition_id}/versions/{version}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/images/custom` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/images/custom/{image_definition_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/images/custom/{image_definition_id}/versions` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/hosted-runners/images/custom/{image_definition_id}/versions/{version}` | read | UAT, IAT | ✗ |

## Organization permissions for "Issue Fields"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/issue-fields` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/issue-fields/{issue_field_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/issue-fields/{issue_field_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/issue-fields` | read | UAT, IAT | ✗ |

## Organization permissions for "Issue Types"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/issue-types` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/issue-types/{issue_type_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/issue-types/{issue_type_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/issue-types` | read | UAT, IAT | ✗ |

## Organization permissions for "Members"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/invitations` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/invitations/{invitation_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/members/{username}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/memberships/{username}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/memberships/{username}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/organization-roles/teams/{team_slug}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/organization-roles/teams/{team_slug}/{role_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/organization-roles/teams/{team_slug}/{role_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/organization-roles/users/{username}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/organization-roles/users/{username}/{role_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/organization-roles/users/{username}/{role_id}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/outside_collaborators/{username}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/outside_collaborators/{username}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/public_members/{username}` | write | UAT | ✗ |
| `DELETE /orgs/{org}/public_members/{username}` | write | UAT | ✗ |
| `POST /orgs/{org}/teams` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/teams/{team_slug}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/teams/{team_slug}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/teams/{team_slug}/memberships/{username}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/teams/{team_slug}/memberships/{username}` | write | UAT, IAT | ✗ |
| `PATCH /teams/{team_id}` | write | UAT, IAT | ✗ |
| `DELETE /teams/{team_id}` | write | UAT, IAT | ✗ |
| `PUT /teams/{team_id}/members/{username}` | write | UAT, IAT | ✗ |
| `DELETE /teams/{team_id}/members/{username}` | write | UAT, IAT | ✗ |
| `PUT /teams/{team_id}/memberships/{username}` | write | UAT, IAT | ✗ |
| `DELETE /teams/{team_id}/memberships/{username}` | write | UAT, IAT | ✗ |
| `PATCH /user/memberships/orgs/{org}` | write | UAT | ✗ |
| `GET /orgs/{org}/failed_invitations` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/invitations` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/invitations/{invitation_id}/teams` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/members` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/members/{username}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/memberships/{username}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/organization-roles/{role_id}/teams` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/organization-roles/{role_id}/users` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/outside_collaborators` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/public_members` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/public_members/{username}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/teams` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/teams/{team_slug}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/teams/{team_slug}/invitations` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/teams/{team_slug}/members` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/teams/{team_slug}/memberships/{username}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/teams/{team_slug}/repos` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}` | read | UAT, IAT | ✓ |
| `PUT /orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}` | read | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/teams/{team_slug}/teams` | read | UAT, IAT | ✗ |
| `GET /teams/{team_id}` | read | UAT, IAT | ✗ |
| `GET /teams/{team_id}/invitations` | read | UAT, IAT | ✗ |
| `GET /teams/{team_id}/members` | read | UAT, IAT | ✗ |
| `GET /teams/{team_id}/members/{username}` | read | UAT, IAT | ✗ |
| `GET /teams/{team_id}/memberships/{username}` | read | UAT, IAT | ✗ |
| `GET /teams/{team_id}/repos` | read | UAT, IAT | ✗ |
| `GET /teams/{team_id}/repos/{owner}/{repo}` | read | UAT, IAT | ✓ |
| `PUT /teams/{team_id}/repos/{owner}/{repo}` | read | UAT, IAT | ✓ |
| `DELETE /teams/{team_id}/repos/{owner}/{repo}` | read | UAT, IAT | ✓ |
| `GET /teams/{team_id}/teams` | read | UAT, IAT | ✗ |
| `GET /user/memberships/orgs/{org}` | read | UAT | ✗ |

## Organization permissions for "Network configurations"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/settings/network-configurations` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/settings/network-configurations/{network_configuration_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/settings/network-configurations/{network_configuration_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/settings/network-configurations` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/settings/network-configurations/{network_configuration_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/settings/network-settings/{network_settings_id}` | read | UAT, IAT | ✗ |

## Organization permissions for "Organization Copilot metrics"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /orgs/{org}/copilot/metrics/reports/organization-1-day` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/metrics/reports/organization-28-day/latest` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/metrics/reports/repos-1-day` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/metrics/reports/user-teams-1-day` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/metrics/reports/users-1-day` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/copilot/metrics/reports/users-28-day/latest` | read | UAT, IAT | ✗ |

## Organization permissions for "Organization codespaces secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/codespaces/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/codespaces/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/codespaces/secrets/{secret_name}/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/codespaces/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/codespaces/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/codespaces/secrets` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/codespaces/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/codespaces/secrets/{secret_name}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/codespaces/secrets/{secret_name}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Organization codespaces settings"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/codespaces/access` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/codespaces/access/selected_users` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/codespaces/access/selected_users` | write | UAT, IAT | ✗ |

## Organization permissions for "Organization codespaces"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `DELETE /orgs/{org}/members/{username}/codespaces/{codespace_name}` | write | UAT, IAT | ✓ |
| `POST /orgs/{org}/members/{username}/codespaces/{codespace_name}/stop` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/codespaces` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/members/{username}/codespaces` | read | UAT, IAT | ✓ |

## Organization permissions for "Organization dependabot secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/dependabot/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/dependabot/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/dependabot/secrets/{secret_name}/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/dependabot/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/dependabot/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/dependabot/secrets` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/dependabot/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/dependabot/secrets/{secret_name}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/dependabot/secrets/{secret_name}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Organization private registries"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/private-registries` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/private-registries/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/private-registries/{secret_name}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/private-registries` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/private-registries/public-key` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/private-registries/{secret_name}` | read | UAT, IAT | ✗ |

## Organization permissions for "Personal access token requests"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/personal-access-token-requests` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/personal-access-token-requests/{pat_request_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/personal-access-token-requests` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/personal-access-token-requests/{pat_request_id}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Personal access tokens"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/personal-access-tokens` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/personal-access-tokens/{pat_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/personal-access-tokens` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/personal-access-tokens/{pat_id}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Projects"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/projectsV2/{project_number}/drafts` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/projectsV2/{project_number}/fields` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/projectsV2/{project_number}/items` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/projectsV2/{project_number}/items/{item_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/projectsV2/{project_number}/items/{item_id}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/projectsV2/{project_number}/views` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/projectsV2` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/projectsV2/{project_number}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/projectsV2/{project_number}/fields` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/projectsV2/{project_number}/fields/{field_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/projectsV2/{project_number}/items` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/projectsV2/{project_number}/items/{item_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/projectsV2/{project_number}/views/{view_number}/items` | read | UAT, IAT | ✗ |

## Organization permissions for "Secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /orgs/{org}/actions/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/secrets/{secret_name}/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/actions/secrets/{secret_name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/actions/secrets` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/secrets/{secret_name}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/secrets/{secret_name}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Self-hosted runners"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/actions/runner-groups` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/actions/runner-groups/{runner_group_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/runner-groups/{runner_group_id}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/runner-groups/{runner_group_id}/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/runner-groups/{runner_group_id}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/actions/runner-groups/{runner_group_id}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `PUT /orgs/{org}/actions/runner-groups/{runner_group_id}/runners` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/runner-groups/{runner_group_id}/runners/{runner_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/runner-groups/{runner_group_id}/runners/{runner_id}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/actions/runners/generate-jitconfig` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/actions/runners/registration-token` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/actions/runners/remove-token` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/runners/{runner_id}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/actions/runners/{runner_id}/labels` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/runners/{runner_id}/labels` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/runners/{runner_id}/labels` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/runners/{runner_id}/labels/{name}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runner-groups` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runner-groups/{runner_group_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runner-groups/{runner_group_id}/hosted-runners` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runner-groups/{runner_group_id}/repositories` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runner-groups/{runner_group_id}/runners` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runners` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runners/deprecations/{version}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runners/downloads` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runners/{runner_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/runners/{runner_id}/labels` | read | UAT, IAT | ✗ |

## Organization permissions for "Variables"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/actions/variables` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/actions/variables/{name}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/actions/variables/{name}` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/variables/{name}/repositories` | write | UAT, IAT | ✗ |
| `PUT /orgs/{org}/actions/variables/{name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/actions/variables/{name}/repositories/{repository_id}` | write | UAT, IAT | ✓ |
| `GET /orgs/{org}/actions/variables` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/variables/{name}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/actions/variables/{name}/repositories` | read | UAT, IAT | ✗ |

## Organization permissions for "Webhooks"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/hooks` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/hooks/{hook_id}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/hooks/{hook_id}` | write | UAT, IAT | ✗ |
| `PATCH /orgs/{org}/hooks/{hook_id}/config` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/hooks/{hook_id}/deliveries/{delivery_id}/attempts` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/hooks/{hook_id}/pings` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/hooks` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/hooks/{hook_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/hooks/{hook_id}/config` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/hooks/{hook_id}/deliveries` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/hooks/{hook_id}/deliveries/{delivery_id}` | read | UAT, IAT | ✗ |

## Repository permissions for "Actions"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `DELETE /repos/{owner}/{repo}/actions/artifacts/{artifact_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/caches` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/caches/{cache_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/jobs/{job_id}/rerun` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/oidc/customization/sub` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/runs/{run_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runs/{run_id}/approve` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runs/{run_id}/cancel` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runs/{run_id}/force-cancel` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/runs/{run_id}/logs` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/workflows/{workflow_id}/disable` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/workflows/{workflow_id}/enable` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/artifacts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/{archive_format}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/cache/storage-limit` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/cache/usage` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/caches` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/concurrency_groups` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/concurrency_groups/{concurrency_group_name}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/jobs/{job_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/jobs/{job_id}/steps/{step_number}/logs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/oidc/customization/sub` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/approvals` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/jobs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/logs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/concurrency_groups` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/logs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runs/{run_id}/timing` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/workflows` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/timing` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/deployment-branch-policies` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/deployment-branch-policies/{branch_policy_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/deployment_protection_rules` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/deployment_protection_rules/{protection_rule_id}` | read | UAT, IAT | ✗ |

## Repository permissions for "Administration"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/repos` | write | UAT, IAT | ✓ |
| `PUT /orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}` | write | UAT, IAT | ✓ |
| `DELETE /orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/cache/retention-limit` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/cache/storage-limit` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/permissions` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/permissions/access` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/permissions/artifact-and-log-retention` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/permissions/fork-pr-workflows-private-repos` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/permissions/selected-actions` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/permissions/workflow` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/policies` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/policies` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/policies/{policy_id}` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/policies/{policy_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/policies/{policy_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runners/generate-jitconfig` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runners/registration-token` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runners/remove-token` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/runners/{runner_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runners/{runner_id}/labels` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/actions/runners/{runner_id}/labels` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/runners/{runner_id}/labels` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/runners/{runner_id}/labels/{name}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/autolinks` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/autolinks/{autolink_id}` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/automated-security-fixes` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/automated-security-fixes` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/branches/{branch}/protection` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/branches/{branch}/protection/enforce_admins` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/enforce_admins` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/branches/{branch}/protection/required_pull_request_reviews` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/required_pull_request_reviews` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/branches/{branch}/protection/required_signatures` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/required_signatures` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks/contexts` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks/contexts` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks/contexts` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/restrictions` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/apps` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/apps` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/apps` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/teams` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/teams` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/teams` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/users` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/users` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/users` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-quality/setup` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/code-quality/setup` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/code-scanning/ai-scan` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/code-scanning/default-setup` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/collaborators/{username}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/collaborators/{username}` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/environments/{environment_name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/environments/{environment_name}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/environments/{environment_name}/deployment-branch-policies` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/environments/{environment_name}/deployment-branch-policies/{branch_policy_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/environments/{environment_name}/deployment-branch-policies/{branch_policy_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/environments/{environment_name}/deployment_protection_rules` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/environments/{environment_name}/deployment_protection_rules/{protection_rule_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/forks` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/immutable-releases` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/immutable-releases` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/interaction-limits` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/interaction-limits` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/interaction-limits/pulls/bypass-list` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/interaction-limits/pulls/bypass-list` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/interaction-limits/pulls/bypass-list` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/interaction-limits/pulls/creation-cap` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/interaction-limits/pulls/creation-cap` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/invitations/{invitation_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/invitations/{invitation_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/keys` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/keys/{key_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pages` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/pages` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/pages` | write | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/pages/health` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/private-vulnerability-reporting` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/private-vulnerability-reporting` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/rulesets` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/rulesets/{ruleset_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/rulesets/{ruleset_id}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/rulesets/{ruleset_id}/history` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/rulesets/{ruleset_id}/history/{version_id}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/secret-scanning/custom-patterns` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/secret-scanning/custom-patterns` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/secret-scanning/custom-patterns` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/secret-scanning/custom-patterns/{pattern_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/security-advisories/{ghsa_id}/forks` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/topics` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/transfer` | write | UAT | ✗ |
| `PUT /repos/{owner}/{repo}/vulnerability-alerts` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/vulnerability-alerts` | write | UAT, IAT | ✗ |
| `POST /repos/{template_owner}/{template_repo}/generate` | write | UAT, IAT | ✓ |
| `PUT /teams/{team_id}/repos/{owner}/{repo}` | write | UAT, IAT | ✓ |
| `DELETE /teams/{team_id}/repos/{owner}/{repo}` | write | UAT, IAT | ✓ |
| `POST /user/repos` | write | UAT, IAT | ✓ |
| `PATCH /user/repository_invitations/{invitation_id}` | write | UAT | ✗ |
| `DELETE /user/repository_invitations/{invitation_id}` | write | UAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/cache/retention-limit` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/permissions` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/permissions/access` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/permissions/artifact-and-log-retention` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/permissions/fork-pr-workflows-private-repos` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/permissions/selected-actions` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/permissions/workflow` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runners` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runners/deprecations/{version}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runners/downloads` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runners/{runner_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/runners/{runner_id}/labels` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/autolinks` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/autolinks/{autolink_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/automated-security-fixes` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/enforce_admins` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/required_pull_request_reviews` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/required_signatures` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/required_status_checks/contexts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/restrictions` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/apps` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/teams` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}/protection/restrictions/users` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/default-setup` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-security-configuration` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/deployment_protection_rules/apps` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/immutable-releases` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/interaction-limits` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/invitations` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/keys` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/keys/{key_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/rulesets/rule-suites` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/rulesets/rule-suites/{rule_suite_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/teams` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/traffic/clones` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/traffic/popular/paths` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/traffic/popular/referrers` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/traffic/views` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/vulnerability-alerts` | read | UAT, IAT | ✗ |
| `GET /user/repository_invitations` | read | UAT | ✗ |

## Repository permissions for "Agent secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /repos/{owner}/{repo}/agents/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/agents/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/agents/organization-secrets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/agents/secrets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/agents/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/agents/secrets/{secret_name}` | read | UAT, IAT | ✗ |

## Repository permissions for "Agent variables"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/agents/variables` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/agents/variables/{name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/agents/variables/{name}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/agents/organization-variables` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/agents/variables` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/agents/variables/{name}` | read | UAT, IAT | ✗ |

## Repository permissions for "Artifact metadata"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/artifacts/metadata/deployment-record` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/artifacts/metadata/deployment-record/cluster/{cluster}` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/artifacts/metadata/deployment-record/cluster/{cluster}/jobs` | write | UAT, IAT | ✗ |
| `POST /orgs/{org}/artifacts/metadata/storage-record` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/artifacts/metadata/deployment-record/cluster/{cluster}/jobs/{job_id}` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/artifacts/{subject_digest}/metadata/deployment-records` | read | UAT, IAT | ✗ |
| `GET /orgs/{org}/artifacts/{subject_digest}/metadata/storage-records` | read | UAT, IAT | ✗ |

## Repository permissions for "Attestations"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/attestations/delete-request` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/attestations/digest/{subject_digest}` | write | UAT, IAT | ✗ |
| `DELETE /orgs/{org}/attestations/{attestation_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/attestations` | write | UAT, IAT | ✗ |
| `POST /users/{username}/attestations/delete-request` | write | UAT, IAT | ✗ |
| `DELETE /users/{username}/attestations/digest/{subject_digest}` | write | UAT, IAT | ✗ |
| `DELETE /users/{username}/attestations/{attestation_id}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/attestations/repositories` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/attestations/{subject_digest}` | read | UAT, IAT | ✗ |

## Repository permissions for "Checks"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/check-runs` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/check-runs/{check_run_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/check-runs/{check_run_id}/rerequest` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/check-suites` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/check-suites/preferences` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/check-suites/{check_suite_id}/rerequest` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/check-runs/{check_run_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/check-runs/{check_run_id}/annotations` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/check-suites/{check_suite_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits/{ref}/check-suites` | read | UAT, IAT | ✗ |

## Repository permissions for "Code quality"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /repos/{owner}/{repo}/code-quality/findings` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-quality/findings/{finding_number}` | read | UAT, IAT | ✗ |

## Repository permissions for "Code scanning alerts"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /repos/{owner}/{repo}/code-scanning/alerts/{alert_number}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/code-scanning/alerts/{alert_number}/autofix` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/code-scanning/analyses/{analysis_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/code-scanning/sarifs` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/code-scanning/alerts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/ai-scan` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/alerts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/alerts/{alert_number}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/alerts/{alert_number}/autofix` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/alerts/{alert_number}/instances` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/analyses` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/analyses/{analysis_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/sarifs/{sarif_id}` | read | UAT, IAT | ✗ |

## Repository permissions for "Codespaces lifecycle admin"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/members/{username}/codespaces/{codespace_name}/stop` | write | UAT, IAT | ✓ |
| `POST /user/codespaces/{codespace_name}/exports` | write | UAT | ✗ |
| `POST /user/codespaces/{codespace_name}/start` | write | UAT | ✗ |
| `POST /user/codespaces/{codespace_name}/stop` | write | UAT | ✗ |
| `GET /user/codespaces/{codespace_name}/exports/{export_id}` | read | UAT | ✗ |

## Repository permissions for "Codespaces metadata"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /repos/{owner}/{repo}/codespaces/devcontainers` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/codespaces/machines` | read | UAT, IAT | ✗ |
| `GET /user/codespaces/{codespace_name}/machines` | read | UAT | ✗ |

## Repository permissions for "Codespaces secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /repos/{owner}/{repo}/codespaces/secrets` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/codespaces/secrets/public-key` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/codespaces/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/codespaces/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/codespaces/secrets/{secret_name}` | write | UAT, IAT | ✗ |

## Repository permissions for "Codespaces"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `DELETE /orgs/{org}/members/{username}/codespaces/{codespace_name}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/codespaces` | write | UAT | ✗ |
| `GET /repos/{owner}/{repo}/codespaces/new` | write | UAT | ✗ |
| `GET /repos/{owner}/{repo}/codespaces/permissions_check` | write | UAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/codespaces` | write | UAT | ✗ |
| `POST /user/codespaces` | write | UAT | ✗ |
| `PATCH /user/codespaces/{codespace_name}` | write | UAT | ✗ |
| `DELETE /user/codespaces/{codespace_name}` | write | UAT | ✗ |
| `POST /user/codespaces/{codespace_name}/publish` | write | UAT | ✗ |
| `GET /orgs/{org}/codespaces` | read | UAT, IAT | ✓ |
| `GET /orgs/{org}/members/{username}/codespaces` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/codespaces` | read | UAT | ✗ |
| `GET /user/codespaces` | read | UAT | ✗ |
| `GET /user/codespaces/{codespace_name}` | read | UAT | ✗ |

## Repository permissions for "Commit statuses"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/statuses/{sha}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits/{ref}/status` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits/{ref}/statuses` | read | UAT, IAT | ✗ |

## Repository permissions for "Contents"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/branches/{branch}/rename` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/code-scanning/alerts/{alert_number}/autofix/commits` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/code-scanning/codeql/databases/{language}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/code-scanning/codeql/variant-analyses` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/comments/{comment_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/comments/{comment_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/comments/{comment_id}/reactions` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/comments/{comment_id}/reactions/{reaction_id}` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/contents/{path}` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/contents/{path}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/contents/{path}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/contents/{path}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/dependency-graph/snapshots` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/dispatches` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/git/blobs` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/git/commits` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/git/refs` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/git/refs` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/git/refs/{ref}` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/git/refs/{ref}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/git/refs/{ref}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/git/tags` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/git/trees` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/import` | write | UAT | ✗ |
| `PATCH /repos/{owner}/{repo}/import` | write | UAT | ✗ |
| `DELETE /repos/{owner}/{repo}/import` | write | UAT | ✗ |
| `PATCH /repos/{owner}/{repo}/import/authors/{author_id}` | write | UAT | ✗ |
| `PATCH /repos/{owner}/{repo}/import/lfs` | write | UAT | ✗ |
| `POST /repos/{owner}/{repo}/merge-upstream` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/merges` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge-async` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/merge-async/{uuid}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/releases` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/releases` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/releases/assets/{asset_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/releases/assets/{asset_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/releases/generate-notes` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/releases/{release_id}` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/releases/{release_id}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/releases/{release_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/secret-scanning/push-protection-bypasses` | write | UAT | ✗ |
| `GET /repos/{owner}/{repo}/stargazers` | write | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/subscribers` | write | UAT, IAT | ✓ |
| `POST /markdown` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/activity` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/branches/{branch}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/codeql/databases` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/codeql/databases/{language}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/codeql/variant-analyses/{codeql_variant_analysis_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/code-scanning/codeql/variant-analyses/{codeql_variant_analysis_id}/repos/{repo_owner}/{repo_name}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/codeowners/errors` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits/{commit_sha}/branches-where-head` | read | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/commits/{commit_sha}/comments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits/{ref}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/community/profile` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/compare/{basehead}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/contents/{path}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependency-graph/compare/{basehead}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependency-graph/sbom` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependency-graph/sbom/fetch-report/{sbom_uuid}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependency-graph/sbom/generate-report` | read | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/forks` | read | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/forks` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/git/blobs/{file_sha}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/git/commits/{commit_sha}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/git/matching-refs/{ref}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/git/ref/{ref}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/git/tags/{tag_sha}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/git/trees/{tree_sha}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/import` | read | UAT | ✗ |
| `GET /repos/{owner}/{repo}/import/authors` | read | UAT | ✗ |
| `GET /repos/{owner}/{repo}/import/large_files` | read | UAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/readme` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/readme/{dir}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/releases` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/releases/assets/{asset_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/releases/latest` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/releases/tags/{tag}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/releases/{release_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/releases/{release_id}/assets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/tarball/{ref}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/zipball/{ref}` | read | UAT, IAT | ✗ |
| `POST /repos/{template_owner}/{template_repo}/generate` | read | UAT, IAT | ✓ |
| `POST /repos/{template_owner}/{template_repo}/generate` | read | UAT, IAT | ✓ |

## Repository permissions for "Copilot agent settings"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /repos/{owner}/{repo}/copilot/cloud-agent/configuration` | read | UAT, IAT | ✗ |

## Repository permissions for "Custom properties"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /repos/{owner}/{repo}/properties/values` | write | UAT, IAT | ✗ |

## Repository permissions for "Dependabot alerts"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /repos/{owner}/{repo}/dependabot/alerts/{alert_number}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/dependabot/alerts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependabot/alerts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependabot/alerts/{alert_number}` | read | UAT, IAT | ✗ |

## Repository permissions for "Dependabot secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /repos/{owner}/{repo}/dependabot/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/dependabot/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependabot/secrets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependabot/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/dependabot/secrets/{secret_name}` | read | UAT, IAT | ✗ |

## Repository permissions for "Deployments"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/actions/runs/{run_id}/deployment_protection_rule` | write | IAT | ✗ |
| `POST /repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/deployments` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/deployments/{deployment_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/deployments/{deployment_id}/statuses` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/deployments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/deployments/{deployment_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/deployments/{deployment_id}/statuses` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/deployments/{deployment_id}/statuses/{status_id}` | read | UAT, IAT | ✗ |

## Repository permissions for "Environments"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /repos/{owner}/{repo}/environments/{environment_name}/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/environments/{environment_name}/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/environments/{environment_name}/variables` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/environments/{environment_name}/variables/{name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/environments/{environment_name}/variables/{name}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/secrets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/secrets/{secret_name}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/variables` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/environments/{environment_name}/variables/{name}` | read | UAT, IAT | ✗ |

## Repository permissions for "GitHub App installation repository access"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /user/installations/{installation_id}/repositories/{repository_id}` | write | UAT, IAT | ✗ |
| `DELETE /user/installations/{installation_id}/repositories/{repository_id}` | write | UAT, IAT | ✗ |

## Repository permissions for "Issues"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/issues` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/issues/comments/{comment_id}/pin` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}/pin` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions/{reaction_id}` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/issues/{issue_number}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/assignees` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/assignees` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocked_by` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocked_by/{issue_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values/{issue_field_id}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/labels` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/issues/{issue_number}/labels` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{name}` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/issues/{issue_number}/lock` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/lock` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/reactions` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/reactions/{reaction_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/relates_to` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/relates_to/{issue_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/sub_issue` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/sub_issues` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/issues/{issue_number}/sub_issues/priority` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/suggestions/{suggestion_id}/approve` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/suggestions/{suggestion_id}/dismiss` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/labels` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/labels/{name}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/labels/{name}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/milestones` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/milestones/{milestone_number}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/milestones/{milestone_number}` | write | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/assignees` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/assignees/{assignee}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/comments` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/comments/{comment_id}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/events` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/events/{event_id}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/assignees/{assignee}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/comments` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocked_by` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/dependencies/blocking` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/events` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/labels` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/parent` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/reactions` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/relates_to` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/sub_issues` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/suggestions` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/timeline` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/labels` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/labels/{name}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/milestones` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/milestones/{milestone_number}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/milestones/{milestone_number}/labels` | read | UAT, IAT | ✓ |

## Repository permissions for "Metadata"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /orgs/{org}/repos` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/collaborators` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/collaborators/{username}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/collaborators/{username}/permission` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/comments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/comments/{comment_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/comments/{comment_id}/reactions` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/commits/{commit_sha}/comments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/contributors` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/events` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/forks` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/hash-algorithm` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issue-types` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/languages` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/license` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/private-vulnerability-reporting` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/properties/values` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/rules/branches/{branch}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/rulesets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/rulesets/{ruleset_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stargazers/count` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stargazers/history` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stats/code_frequency` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stats/commit_activity` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stats/contributors` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stats/participation` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stats/punch_card` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/tags` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/topics` | read | UAT, IAT | ✗ |
| `GET /repositories` | read | UAT, IAT | ✗ |
| `GET /search/labels` | read | UAT, IAT | ✗ |
| `GET /user/installations/{installation_id}/repositories` | read | UAT | ✗ |
| `GET /user/repos` | read | UAT | ✗ |
| `GET /users/{username}/repos` | read | UAT, IAT | ✗ |

## Repository permissions for "Pages"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/pages` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/pages` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/pages` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/pages/builds` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pages/deployments` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pages/deployments/{pages_deployment_id}/cancel` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pages/health` | write | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/pages` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pages/builds` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pages/builds/latest` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pages/builds/{build_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pages/deployments/{pages_deployment_id}` | read | UAT, IAT | ✗ |

## Repository permissions for "Pull requests"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /repos/{owner}/{repo}/issues/comments/{comment_id}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/comments/{comment_id}` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/issues/{issue_number}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/assignees` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/assignees` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/issue-field-values/{issue_field_id}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/labels` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/issues/{issue_number}/labels` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{name}` | write | UAT, IAT | ✓ |
| `PUT /repos/{owner}/{repo}/issues/{issue_number}/lock` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/issues/{issue_number}/lock` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/suggestions/{suggestion_id}/approve` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/suggestions/{suggestion_id}/dismiss` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/labels` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/labels/{name}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/labels/{name}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/milestones` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/milestones/{milestone_number}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/milestones/{milestone_number}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/pulls` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/pulls/comments/{comment_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/pulls/comments/{comment_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions/{reaction_id}` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/pulls/{pull_number}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers/rerequest` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/dismissals` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/events` | write | UAT, IAT | ✗ |
| `PUT /repos/{owner}/{repo}/pulls/{pull_number}/update-branch` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/stacks` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/stacks/{stack_number}/add` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/stacks/{stack_number}/unstack` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/assignees` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/assignees/{assignee}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/issues/comments` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/comments/{comment_id}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/events/{event_id}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/assignees/{assignee}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/comments` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/events` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/labels` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/suggestions` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/timeline` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/labels` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/labels/{name}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/milestones` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/milestones/{milestone_number}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/milestones/{milestone_number}/labels` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/pulls` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/comments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/comments/{comment_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}` | read | UAT, IAT | ✓ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/commits` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/files` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/merge` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/comments` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stacks` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/stacks/{stack_number}` | read | UAT, IAT | ✗ |

## Repository permissions for "Repository creation"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /orgs/{org}/repos` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/forks` | write | UAT, IAT | ✓ |
| `POST /repos/{template_owner}/{template_repo}/generate` | write | UAT, IAT | ✓ |
| `POST /user/repos` | write | UAT, IAT | ✓ |

## Repository permissions for "Repository security advisories"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /orgs/{org}/security-advisories` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/security-advisories` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/security-advisories/reports` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/security-advisories/{ghsa_id}` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/security-advisories/{ghsa_id}/cve` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/security-advisories` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/security-advisories/{ghsa_id}` | read | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/security-advisories/{ghsa_id}/forks` | read | UAT, IAT | ✓ |

## Repository permissions for "Secret scanning alerts"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /repos/{owner}/{repo}/secret-scanning/alerts/{alert_number}` | write | UAT, IAT | ✗ |
| `GET /orgs/{org}/secret-scanning/alerts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/secret-scanning/alerts` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/secret-scanning/alerts/{alert_number}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/secret-scanning/alerts/{alert_number}/locations` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/secret-scanning/scan-history` | read | UAT, IAT | ✗ |

## Repository permissions for "Secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /repos/{owner}/{repo}/actions/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/secrets/{secret_name}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/organization-secrets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/secrets` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/secrets/public-key` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/secrets/{secret_name}` | read | UAT, IAT | ✗ |

## Repository permissions for "Variables"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/actions/variables` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/actions/variables/{name}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/actions/variables/{name}` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/organization-variables` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/variables` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/actions/variables/{name}` | read | UAT, IAT | ✗ |

## Repository permissions for "Webhooks"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /repos/{owner}/{repo}/hooks` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/hooks/{hook_id}` | write | UAT, IAT | ✗ |
| `DELETE /repos/{owner}/{repo}/hooks/{hook_id}` | write | UAT, IAT | ✗ |
| `PATCH /repos/{owner}/{repo}/hooks/{hook_id}/config` | write | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/hooks/{hook_id}/deliveries/{delivery_id}/attempts` | write | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/hooks` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/hooks/{hook_id}` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/hooks/{hook_id}/config` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/hooks/{hook_id}/deliveries` | read | UAT, IAT | ✗ |
| `GET /repos/{owner}/{repo}/hooks/{hook_id}/deliveries/{delivery_id}` | read | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/hooks/{hook_id}/pings` | read | UAT, IAT | ✗ |
| `POST /repos/{owner}/{repo}/hooks/{hook_id}/tests` | read | UAT, IAT | ✗ |

## Repository permissions for "Workflows"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /repos/{owner}/{repo}/contents/{path}` | write | UAT, IAT | ✓ |
| `DELETE /repos/{owner}/{repo}/contents/{path}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/git/refs` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/git/refs/{ref}` | write | UAT, IAT | ✓ |
| `POST /repos/{owner}/{repo}/releases` | write | UAT, IAT | ✓ |
| `PATCH /repos/{owner}/{repo}/releases/{release_id}` | write | UAT, IAT | ✓ |

## User permissions for "Block another user"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /user/blocks/{username}` | write | UAT | ✗ |
| `DELETE /user/blocks/{username}` | write | UAT | ✗ |
| `GET /user/blocks` | read | UAT | ✗ |
| `GET /user/blocks/{username}` | read | UAT | ✗ |

## User permissions for "Codespaces user secrets"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /user/codespaces/secrets/{secret_name}` | write | UAT | ✗ |
| `DELETE /user/codespaces/secrets/{secret_name}` | write | UAT | ✗ |
| `PUT /user/codespaces/secrets/{secret_name}/repositories` | write | UAT | ✗ |
| `PUT /user/codespaces/secrets/{secret_name}/repositories/{repository_id}` | write | UAT | ✓ |
| `DELETE /user/codespaces/secrets/{secret_name}/repositories/{repository_id}` | write | UAT | ✓ |
| `GET /user/codespaces/secrets` | read | UAT | ✗ |
| `GET /user/codespaces/secrets/public-key` | read | UAT | ✗ |
| `GET /user/codespaces/secrets/{secret_name}` | read | UAT | ✗ |
| `GET /user/codespaces/secrets/{secret_name}/repositories` | read | UAT | ✗ |

## User permissions for "Email addresses"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /user/email/visibility` | write | UAT | ✗ |
| `POST /user/emails` | write | UAT | ✗ |
| `DELETE /user/emails` | write | UAT | ✗ |
| `GET /user/emails` | read | UAT | ✗ |
| `GET /user/public_emails` | read | UAT | ✗ |

## User permissions for "Followers"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /user/following/{username}` | write | UAT | ✗ |
| `DELETE /user/following/{username}` | write | UAT | ✗ |
| `GET /user/followers` | read | UAT | ✗ |
| `GET /user/following` | read | UAT | ✗ |
| `GET /user/following/{username}` | read | UAT | ✗ |

## User permissions for "GPG keys"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /user/gpg_keys` | write | UAT | ✗ |
| `DELETE /user/gpg_keys/{gpg_key_id}` | write | UAT | ✗ |
| `GET /user/gpg_keys` | read | UAT | ✗ |
| `GET /user/gpg_keys/{gpg_key_id}` | read | UAT | ✗ |

## User permissions for "Gists"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /gists` | write | UAT | ✗ |
| `PATCH /gists/{gist_id}` | write | UAT | ✗ |
| `DELETE /gists/{gist_id}` | write | UAT | ✗ |
| `POST /gists/{gist_id}/comments` | write | UAT | ✗ |
| `PATCH /gists/{gist_id}/comments/{comment_id}` | write | UAT | ✗ |
| `DELETE /gists/{gist_id}/comments/{comment_id}` | write | UAT | ✗ |
| `POST /gists/{gist_id}/forks` | write | UAT | ✗ |
| `PUT /gists/{gist_id}/star` | write | UAT | ✗ |
| `DELETE /gists/{gist_id}/star` | write | UAT | ✗ |

## User permissions for "Git SSH keys"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /user/keys` | write | UAT | ✗ |
| `DELETE /user/keys/{key_id}` | write | UAT | ✗ |
| `GET /user/keys` | read | UAT | ✗ |
| `GET /user/keys/{key_id}` | read | UAT | ✗ |
| `GET /users/{username}/keys` | read | UAT, IAT | ✗ |

## User permissions for "Interaction limits"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /user/interaction-limits` | write | UAT | ✗ |
| `DELETE /user/interaction-limits` | write | UAT | ✗ |
| `GET /user/interaction-limits` | read | UAT | ✗ |

## User permissions for "Plan"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /users/{username}/settings/billing/ai_credit/usage` | read | UAT | ✗ |
| `GET /users/{username}/settings/billing/premium_request/usage` | read | UAT | ✗ |
| `GET /users/{username}/settings/billing/usage` | read | UAT | ✗ |
| `GET /users/{username}/settings/billing/usage/summary` | read | UAT | ✗ |

## User permissions for "Private repository invitations"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /repos/{owner}/{repo}/invitations` | read | UAT, IAT | ✓ |

## User permissions for "Profile"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PATCH /user` | write | UAT | ✗ |
| `POST /user/social_accounts` | write | UAT | ✗ |
| `DELETE /user/social_accounts` | write | UAT | ✗ |

## User permissions for "SSH signing keys"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `POST /user/ssh_signing_keys` | write | UAT | ✗ |
| `DELETE /user/ssh_signing_keys/{ssh_signing_key_id}` | write | UAT | ✗ |
| `GET /user/ssh_signing_keys` | read | UAT | ✗ |
| `GET /user/ssh_signing_keys/{ssh_signing_key_id}` | read | UAT | ✗ |

## User permissions for "Starring"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `PUT /user/starred/{owner}/{repo}` | write | UAT | ✓ |
| `DELETE /user/starred/{owner}/{repo}` | write | UAT | ✓ |
| `GET /user/starred` | read | UAT | ✗ |
| `GET /user/starred/{owner}/{repo}` | read | UAT | ✓ |
| `GET /users/{username}/starred` | read | UAT, IAT | ✗ |

## User permissions for "Watching"

| Endpoint | Access | Tokens | Additional Permissions |
|----------|--------|--------|------------------------|
| `GET /user/subscriptions` | read | UAT | ✗ |
| `GET /users/{username}/subscriptions` | read | UAT, IAT | ✗ |

