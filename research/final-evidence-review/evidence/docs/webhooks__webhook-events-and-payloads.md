# Webhook events and payloads

Learn about when each webhook event occurs and what the payload contains.

## About webhook events and payloads

You can create webhooks that subscribe to the events listed on this page. To limit the number of HTTP requests to your server, you should only subscribe to the specific events that you plan on handling. For more information, see [Creating webhooks](/en/webhooks/using-webhooks/creating-webhooks).

Each webhook event on this page includes a description of the webhook properties for that event. If the event has multiple actions, the properties corresponding to each action are included.

Each event is only available to specific types of webhooks. For example, an organization webhook can subscribe to the `team` event, but a repository webhook cannot. The description of each webhook event lists the availability for that event. For more information, see [Types of webhooks](/en/webhooks/types-of-webhooks).

### The `sender` property

Most webhook payloads include a `sender` property identifying the user who triggered the event. Sometimes GitHub can't resolve a specific user, for example when an event comes from an internal process rather than a person, or when the triggering action has no associated user. For some events, such as `check_run` and `check_suite`, this includes actions with no Git push or authenticated API actor.

In these cases, `sender` is populated with the [`ghost` user](https://github.com/ghost), a placeholder account whose `login` is `ghost` and whose `id` isn't tied to a real, current user. Don't assume `sender` always identifies the person who caused an event, and account for the `ghost` user in any security or business logic that relies on it.

### Payload cap

Payloads are capped at 25 MB. If an event generates a larger payload, GitHub will not deliver a payload for that webhook event. This may happen, for example, on a `create` event if many branches or tags are pushed at once. We suggest monitoring your payload size to ensure delivery.

### Delivery headers

HTTP POST payloads that are delivered to your webhook's configured URL endpoint will contain several special headers:

* `X-GitHub-Hook-ID`: The unique identifier of the webhook.
* `X-GitHub-Event`: The name of the event that triggered the delivery.
* `X-GitHub-Delivery`: A globally unique identifier (GUID) to identify the event.
* `X-Hub-Signature`: This header is sent if the webhook is configured with a `secret`. This is the HMAC hex digest of the request body, and is generated using the SHA-1 hash function and the `secret` as the HMAC `key`. `X-Hub-Signature` is provided for compatibility with existing integrations. We recommend that you use the more secure `X-Hub-Signature-256` instead.
* `X-Hub-Signature-256`: This header is sent if the webhook is configured with a `secret`. This is the HMAC hex digest of the request body, and is generated using the SHA-256 hash function and the `secret` as the HMAC `key`. For more information, see [Validating webhook deliveries](/en/webhooks/using-webhooks/validating-webhook-deliveries).
* `User-Agent`: This header will always have the prefix `GitHub-Hookshot/`.
* `X-GitHub-Hook-Installation-Target-Type`: The type of resource where the webhook was created.
* `X-GitHub-Hook-Installation-Target-ID`: The unique identifier of the resource where the webhook was created.

To see what each header might look like in a webhook payload, see [Example webhook delivery](#example-webhook-delivery).

### Example webhook delivery

You can choose to have payloads delivered in JSON format (`application/json`) or as URL-encoded data (`x-www-form-urlencoded`). Following is an example of a webhook POST request that uses the JSON format.

```shell
> POST /payload HTTP/1.1

> X-GitHub-Delivery: 72d3162e-cc78-11e3-81ab-4c9367dc0958
> X-Hub-Signature: sha1=7d38cdd689735b008b3c702edd92eea23791c5f6
> X-Hub-Signature-256: sha256=d57c68ca6f92289e6987922ff26938930f6e66a2d161ef06abdf1859230aa23c
> User-Agent: GitHub-Hookshot/044aadd
> Content-Type: application/json
> Content-Length: 6615
> X-GitHub-Event: issues
> X-GitHub-Hook-ID: 292430182
> X-GitHub-Hook-Installation-Target-ID: 79929171
> X-GitHub-Hook-Installation-Target-Type: repository

> {
>   "action": "opened",
>   "issue": {
>     "url": "https://api.github.com/repos/octocat/Hello-World/issues/1347",
>     "number": 1347,
>     ...
>   },
>   "repository" : {
>     "id": 1296269,
>     "full_name": "octocat/Hello-World",
>     "owner": {
>       "login": "octocat",
>       "id": 1,
>       ...
>     },
>     ...
>   },
>   "sender": {
>     "login": "octocat",
>     "id": 1,
>     ...
>   }
> }
```

## Common payload parameters

Most webhook events include these standard parameters:

| Name           | Type     | Description                                                                                                                                                                                                                                       |
| -------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `action`       | `string` | **Required.**                                                                                                                                                                                                                                     |
| `enterprise`   | `object` | An enterprise on GitHub. Webhook payloads contain the enterprise property when the webhook is configured on an enterprise account or an organization that's part of an enterprise account. For more information, see "About enterprise accounts." |
| `installation` | `object` | The GitHub App installation. Webhook payloads contain the installation property when the event is configured for and sent to a GitHub App. For more information, see "Using webhooks with GitHub Apps."                                           |
| `organization` | `object` | A GitHub organization. Webhook payloads contain the organization property when the webhook is configured for an organization, or when the event occurs from activity in a repository owned by an organization.                                    |
| `repository`   | `object` | **Required.** The repository on GitHub where the event occurred. Webhook payloads contain the repository property when the event occurs from activity in a repository.                                                                            |
| `sender`       | `object` | **Required.** A GitHub user.                                                                                                                                                                                                                      |

Events below list only their additional parameters beyond these common ones.

## branch\_protection\_configuration

This event occurs when there is a change to branch protection configurations for a repository.
For more information, see "About protected branches."
For information about using the APIs to manage branch protection rules, see "Branch protection rule" in the GraphQL documentation or "Branch protection" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Administration" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `disabled`, `enabled`

All branch protections were disabled for a repository.

## branch\_protection\_rule

This event occurs when there is activity relating to branch protection rules. For more information, see "About protected branches." For information about the APIs to manage branch protection rules, see the GraphQL documentation or "Branch protection" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Administration" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`

A branch protection rule was created.

#### Webhook payload object parameters

| Name   | Type     | Description                                                                                                                                                                                                                                                                              |
| ------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rule` | `object` | **Required.** The branch protection rule. Includes a name and all the branch protection settings applied to branches that match the name. Binary settings are boolean. Multi-level configurations are one of off, non\_admins, or everyone. Actor and build lists are arrays of strings. |

## check\_run

This event occurs when there is activity relating to a check run. For information about check runs, see "Getting started with the Checks API." For information about the APIs to manage check runs, see the GraphQL API documentation or "Check Runs" in the REST API documentation.
For activity relating to check suites, use the check-suite event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Checks" repository permission. To receive the rerequested and requested\_action event types, the app must have at least write-level access for the "Checks" permission. GitHub Apps with write-level access for the "Checks" permission are automatically subscribed to this webhook event.
Repository and organization webhooks only receive payloads for the created and completed event types in repositories.

The API only looks for pushes in the repository where the check run was created. Pushes to a branch in a forked repository are not detected and return an empty pull\_requests array and a null value for head\_branch.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `completed`, `created`, `requested_action`, `rerequested`

A check run was completed, and a conclusion is available.

#### Webhook payload object parameters

| Name        | Type     | Description                                                        |
| ----------- | -------- | ------------------------------------------------------------------ |
| `check_run` | `object` | **Required.** A check performed on the code of a given code change |

## check\_suite

This event occurs when there is activity relating to a check suite. For information about check suites, see "Getting started with the Checks API." For information about the APIs to manage check suites, see the GraphQL API documentation or "Check Suites" in the REST API documentation.
For activity relating to check runs, use the check\_run event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Checks" permission. To receive the requested and rerequested event types, the app must have at least write-level access for the "Checks" permission. GitHub Apps with write-level access for the "Checks" permission are automatically subscribed to this webhook event.
Repository and organization webhooks only receive payloads for the completed event types in repositories.

The API only looks for pushes in the repository where the check suite was created. Pushes to a branch in a forked repository are not detected and return an empty pull\_requests array and a null value for head\_branch.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `completed`, `requested`, `rerequested`

All check runs in a check suite have completed, and a conclusion is available.

#### Webhook payload object parameters

| Name          | Type     | Description                     |
| ------------- | -------- | ------------------------------- |
| `check_suite` | `object` | **Required.** The check\_suite. |

## code\_scanning\_alert

This event occurs when there is activity relating to code scanning alerts in a repository. For more information, see "About code scanning" and "About code scanning alerts." For information about the API to manage code scanning, see "Code scanning" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Code scanning alerts" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `appeared_in_branch`, `closed_by_user`, `created`, `fixed`, `reopened`, `reopened_by_user`, `updated_assignment`

A previously created code scanning alert appeared in another branch. This can happen when a branch is merged into or created from a branch with a pre-existing code scanning alert.

#### Webhook payload object parameters

| Name         | Type     | Description                                                                                                                                                                                |
| ------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `alert`      | `object` | **Required.** The code scanning alert involved in the event.                                                                                                                               |
| `commit_oid` | `string` | **Required.** The commit SHA of the code scanning alert. When the action is reopened\_by\_user or closed\_by\_user, the event was triggered by the sender and this value will be empty.    |
| `ref`        | `string` | **Required.** The Git reference of the code scanning alert. When the action is reopened\_by\_user or closed\_by\_user, the event was triggered by the sender and this value will be empty. |

## commit\_comment

This event occurs when there is activity relating to commit comments. For more information about commit comments, see "Commenting on a pull request." For information about the APIs to manage commit comments, see the GraphQL API documentation or "Commit comments" in the REST API documentation.
For activity relating to comments on pull request reviews, use the pull\_request\_review\_comment event. For activity relating to issue comments, use the issue\_comment event. For activity relating to discussion comments, use the discussion\_comment event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

Someone commented on a commit.

#### Webhook payload object parameters

| Name      | Type     | Description                                |
| --------- | -------- | ------------------------------------------ |
| `comment` | `object` | **Required.** The commit comment resource. |

## create

This event occurs when a Git branch or tag is created.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.
Notes:

This event will not occur when more than three tags are created at once.
Payloads are capped at 25 MB. If an event generates a larger payload, GitHub will not deliver a payload for that webhook event. This may happen, for example, if many branches or tags are pushed at once. We suggest monitoring your payload size to ensure delivery.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name            | Type             | Description                                                                      |
| --------------- | ---------------- | -------------------------------------------------------------------------------- |
| `description`   | `string or null` | **Required.** The repository's current description.                              |
| `master_branch` | `string`         | **Required.** The name of the repository's default branch (usually main).        |
| `pusher_type`   | `string`         | **Required.** The pusher type for the event. Can be either user or a deploy key. |
| `ref`           | `string`         | **Required.** The git ref resource.                                              |
| `ref_type`      | `string`         | **Required.** The type of Git ref object created in the repository.              |

## custom\_property

This event occurs when there is activity relating to a custom property.
For more information, see "Managing custom properties for repositories in your organization". For information about the APIs to manage custom properties, see "Custom properties" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Custom properties" organization permission.

### Availability

* `business`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `promote_to_enterprise`, `updated`

A new custom property was created.

#### Webhook payload object parameters

| Name         | Type     | Description                                              |
| ------------ | -------- | -------------------------------------------------------- |
| `definition` | `object` | **Required.** Custom property defined on an organization |

## custom\_property\_values

This event occurs when there is activity relating to custom property values for a repository.
For more information, see "Managing custom properties for repositories in your organization". For information about the APIs to manage custom properties for a repository, see "Custom properties" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Custom properties" organization permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

The custom property values of a repository were updated.

#### Webhook payload object parameters

| Name                  | Type               | Description                                                      |
| --------------------- | ------------------ | ---------------------------------------------------------------- |
| `new_property_values` | `array of objects` | **Required.** The new custom property values for the repository. |
| `old_property_values` | `array of objects` | **Required.** The old custom property values for the repository. |

## delete

This event occurs when a Git branch or tag is deleted. To subscribe to all pushes to a repository, including
branch and tag deletions, use the push webhook event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

This event will not occur when more than three tags are deleted at once.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name          | Type     | Description                                                                      |
| ------------- | -------- | -------------------------------------------------------------------------------- |
| `pusher_type` | `string` | **Required.** The pusher type for the event. Can be either user or a deploy key. |
| `ref`         | `string` | **Required.** The git ref resource.                                              |
| `ref_type`    | `string` | **Required.** The type of Git ref object deleted in the repository.              |

## dependabot\_alert

This event occurs when there is activity relating to Dependabot alerts.
For more information about Dependabot alerts, see "About Dependabot alerts." For information about the API to manage Dependabot alerts, see "Dependabot alerts" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Dependabot alerts" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `assignees_changed`, `auto_dismissed`, `auto_reopened`, `created`, `dismissed`, `fixed`, `reintroduced`, `reopened`, `withdrawn`

The assignees for a Dependabot alert were updated.

#### Webhook payload object parameters

| Name    | Type     | Description                       |
| ------- | -------- | --------------------------------- |
| `alert` | `object` | **Required.** A Dependabot alert. |

## deploy\_key

This event occurs when there is activity relating to deploy keys. For more information, see "Managing deploy keys." For information about the APIs to manage deploy keys, see the GraphQL API documentation or "Deploy keys" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Deployments" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`

A deploy key was created.

#### Webhook payload object parameters

| Name  | Type     | Description                            |
| ----- | -------- | -------------------------------------- |
| `key` | `object` | **Required.** The deploy key resource. |

## deployment

This event occurs when there is activity relating to deployments. For more information, see "About deployments." For information about the APIs to manage deployments, see the GraphQL API documentation or "Deployments" in the REST API documentation.
For activity relating to deployment status, use the deployment\_status event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Deployments" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

A deployment was created.

#### Webhook payload object parameters

| Name           | Type             | Description                   |
| -------------- | ---------------- | ----------------------------- |
| `deployment`   | `object`         | **Required.** The deployment. |
| `workflow`     | `object or null` | **Required.**                 |
| `workflow_run` | `object or null` | **Required.**                 |

## deployment\_protection\_rule

This event occurs when there is activity relating to deployment protection rules. For more information, see "Using environments for deployment." For information about the API to manage deployment protection rules, see the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Deployments" repository permission.

### Availability

* `app`

### Webhook payload object

A deployment protection rule was requested for an environment.

#### Webhook payload object parameters

| Name                      | Type               | Description                                                                                                                                |
| ------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `environment`             | `string`           | The name of the environment that has the deployment protection rule.                                                                       |
| `event`                   | `string`           | The event that triggered the deployment protection rule.                                                                                   |
| `sha`                     | `string`           | The commit SHA that triggered the workflow. Always populated from the check suite, regardless of whether a deployment is created.          |
| `ref`                     | `string`           | The ref (branch or tag) that triggered the workflow. Always populated from the check suite, regardless of whether a deployment is created. |
| `deployment_callback_url` | `string`           | The URL to review the deployment protection rule.                                                                                          |
| `deployment`              | `object or null`   | A request for a specific ref(branch,sha,tag) to be deployed                                                                                |
| `pull_requests`           | `array of objects` |                                                                                                                                            |

## deployment\_review

This event occurs when there is activity relating to deployment reviews. For more information, see "About deployments." For information about the APIs to manage deployments, see the GraphQL API documentation or "Deployments" in the REST API documentation.
For activity relating to deployment creation or deployment status, use the deployment or deployment\_status event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Deployments" repository permission.

### Availability

* `app`

### Webhook payload object

**Action type:** `approved`, `rejected`, `requested`

A deployment review was approved.

#### Webhook payload object parameters

| Name                | Type               | Description   |
| ------------------- | ------------------ | ------------- |
| `approver`          | `object`           |               |
| `comment`           | `string`           |               |
| `reviewers`         | `array of objects` |               |
| `since`             | `string`           | **Required.** |
| `workflow_job_run`  | `object`           |               |
| `workflow_job_runs` | `array of objects` |               |
| `workflow_run`      | `object or null`   | **Required.** |

## deployment\_status

This event occurs when there is activity relating to deployment statuses. For more information, see "About deployments." For information about the APIs to manage deployments, see the GraphQL API documentation or "Deployments" in the REST API documentation.
For activity relating to deployment creation, use the deployment event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Deployments" repository permission.

A webhook event is not fired for deployment statuses with an inactive state.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

A new deployment status was created.

#### Webhook payload object parameters

| Name                | Type             | Description                          |
| ------------------- | ---------------- | ------------------------------------ |
| `check_run`         | `object or null` |                                      |
| `deployment`        | `object`         | **Required.** The deployment.        |
| `deployment_status` | `object`         | **Required.** The deployment status. |
| `workflow`          | `object or null` |                                      |
| `workflow_run`      | `object or null` |                                      |

## discussion

This event occurs when there is activity relating to a discussion. For more information about discussions, see "GitHub Discussions." For information about the API to manage discussions, see the GraphQL documentation.
For activity relating to a comment on a discussion, use the discussion\_comment event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Discussions" repository permission.

Webhook events for GitHub Discussions are currently in public preview and subject to change.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `answered`, `category_changed`, `closed`, `created`, `deleted`, `edited`, `labeled`, `locked`, `pinned`, `reopened`, `transferred`, `unanswered`, `unlabeled`, `unlocked`, `unpinned`

A comment on the discussion was marked as the answer.

#### Webhook payload object parameters

| Name         | Type     | Description                                 |
| ------------ | -------- | ------------------------------------------- |
| `answer`     | `object` | **Required.**                               |
| `discussion` | `object` | **Required.** A Discussion in a repository. |

## discussion\_comment

This event occurs when there is activity relating to a comment on a discussion. For more information about discussions, see "GitHub Discussions." For information about the API to manage discussions, see the GraphQL documentation.
For activity relating to a discussion as opposed to comments on a discussion, use the discussion event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Discussions" repository permission.

Webhook events for GitHub Discussions are currently in public preview and subject to change.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`

A comment on a discussion was created.

#### Webhook payload object parameters

| Name         | Type     | Description                                 |
| ------------ | -------- | ------------------------------------------- |
| `comment`    | `object` | **Required.**                               |
| `discussion` | `object` | **Required.** A Discussion in a repository. |

## fork

This event occurs when someone forks a repository. For more information, see "Fork a repo." For information about the API to manage forks, see "Forks" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

### Availability

* `business`
* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name     | Type     | Description                                    |
| -------- | -------- | ---------------------------------------------- |
| `forkee` | `object` | **Required.** The created repository resource. |

## github\_app\_authorization

This event occurs when a user revokes their authorization of a GitHub App. For more information, see "About apps." For information about the API to manage GitHub Apps, see the GraphQL API documentation or "Apps" in the REST API documentation.
A GitHub App receives this webhook by default and cannot unsubscribe from this event.
Anyone can revoke their authorization of a GitHub App from their GitHub account settings page. Revoking the authorization of a GitHub App does not uninstall the GitHub App. You should program your GitHub App so that when it receives this webhook, it stops calling the API on behalf of the person who revoked the token. If your GitHub App continues to use a revoked access token, it will receive the 401 Bad Credentials error. For details about requests with a user access token, which require GitHub App authorization, see "Authenticating with a GitHub App on behalf of a user."

### Availability

* `app`

### Webhook payload object

Someone revoked their authorization of a GitHub App.

## gollum

This event occurs when someone creates or updates a wiki page. For more information, see "About wikis."
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name    | Type               | Description                                |
| ------- | ------------------ | ------------------------------------------ |
| `pages` | `array of objects` | **Required.** The pages that were updated. |

## installation

This event occurs when there is activity relating to a GitHub App installation. All GitHub Apps receive this event by default. You cannot manually subscribe to this event.
For more information about GitHub Apps, see "About apps." For information about the APIs to manage GitHub Apps, see the GraphQL API documentation or "Apps" in the REST API documentation.

### Availability

* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `new_permissions_accepted`, `suspend`, `unsuspend`

Someone installed a GitHub App on a user or organization account.

#### Webhook payload object parameters

| Name           | Type               | Description                                                      |
| -------------- | ------------------ | ---------------------------------------------------------------- |
| `repositories` | `array of objects` | An array of repository objects that the installation can access. |
| `requester`    | `object or null`   |                                                                  |

## installation\_repositories

This event occurs when there is activity relating to which repositories a GitHub App installation can access. All GitHub Apps receive this event by default. You cannot manually subscribe to this event.
For more information about GitHub Apps, see "About apps." For information about the APIs to manage GitHub Apps, see the GraphQL API documentation or "Apps" in the REST API documentation.

### Availability

* `app`

### Webhook payload object

**Action type:** `added`, `removed`

A GitHub App installation was granted access to one or more repositories.

#### Webhook payload object parameters

| Name                   | Type               | Description                                                                                                                                                           |
| ---------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `repositories_added`   | `array of objects` | **Required.** An array of repository objects, which were added to the installation.                                                                                   |
| `repositories_removed` | `array of objects` | **Required.** An array of repository objects, which were removed from the installation. When repository\_selection changes from all to selected, this array is empty. |
| `repository_selection` | `string`           | **Required.** Describe whether all repositories have been selected or there's a selection involved                                                                    |
| `requester`            | `object or null`   | **Required.**                                                                                                                                                         |

## installation\_target

This event occurs when there is activity relating to the user or organization account that a GitHub App is installed on. For more information, see "About apps." For information about the APIs to manage GitHub Apps, see the GraphQL API documentation or "Apps" in the REST API documentation.

### Availability

* `app`

### Webhook payload object

Somebody renamed the user or organization account that a GitHub App is installed on.

#### Webhook payload object parameters

| Name          | Type     | Description   |
| ------------- | -------- | ------------- |
| `account`     | `object` | **Required.** |
| `changes`     | `object` | **Required.** |
| `target_type` | `string` | **Required.** |

## issue\_comment

This event occurs when there is activity relating to a comment on an issue or pull request. For more information about issues and pull requests, see "About issues" and "About pull requests." For information about the APIs to manage issue comments, see the GraphQL documentation or "Issue comments" in the REST API documentation.
For activity relating to an issue as opposed to comments on an issue, use the issue event. For activity related to pull request reviews or pull request review comments, use the pull\_request\_review or pull\_request\_review\_comment events. For more information about the different types of pull request comments, see "Working with comments."
To subscribe to this event, a GitHub App must have at least read-level access for the "Issues" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`, `pinned`, `unpinned`

A comment on an issue or pull request was created.

#### Webhook payload object parameters

| Name      | Type     | Description                                     |
| --------- | -------- | ----------------------------------------------- |
| `comment` | `object` | **Required.** The comment itself.               |
| `issue`   | `object` | **Required.** The issue the comment belongs to. |

## issue\_dependencies

This event occurs when there is activity relating to issue dependencies, such as blocking or blocked-by relationships.
For activity relating to issues more generally, use the issues event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Issues" repository permissions.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `blocked_by_added`, `blocked_by_removed`, `blocking_added`, `blocking_removed`

An issue was marked as blocked by another issue.

#### Webhook payload object parameters

| Name                  | Type     | Description                                                                              |
| --------------------- | -------- | ---------------------------------------------------------------------------------------- |
| `blocked_issue_id`    | `number` | The ID of the blocked issue.                                                             |
| `blocked_issue`       | `object` | Issues are a great way to keep track of tasks, enhancements, and bugs for your projects. |
| `blocking_issue_id`   | `number` | The ID of the blocking issue.                                                            |
| `blocking_issue`      | `object` | Issues are a great way to keep track of tasks, enhancements, and bugs for your projects. |
| `blocking_issue_repo` | `object` | A repository on GitHub.                                                                  |

## issue\_relates\_to

This event occurs when there is activity relating to a "relates to" relationship between two issues.
For relationships between issues in the same repository, GitHub sends one delivery containing both issues. For relationships between issues in different repositories, GitHub sends one delivery for each repository. Each cross-repository delivery contains only the issue in the repository receiving the delivery and omits the related issue, its ID, and its repository details.
For activity relating to issues more generally, use the issues event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Issues" repository permissions.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `relates_to_added`, `relates_to_removed`

An issue was marked as related to another issue.

#### Webhook payload object parameters

| Name               | Type     | Description                                                                               |
| ------------------ | -------- | ----------------------------------------------------------------------------------------- |
| `issue_id`         | `number` | The ID of the issue the relationship was added to.                                        |
| `issue`            | `object` | Issues are a great way to keep track of tasks, enhancements, and bugs for your projects.  |
| `related_issue_id` | `number` | The ID of the related issue. Only present when both issues belong to the same repository. |
| `related_issue`    | `object` | Issues are a great way to keep track of tasks, enhancements, and bugs for your projects.  |

## issues

This event occurs when there is activity relating to an issue. For more information about issues, see "About issues." For information about the APIs to manage issues, see the GraphQL documentation or "Issues" in the REST API documentation.
For activity relating to a comment on an issue, use the issue\_comment event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Issues" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `assigned`, `closed`, `deleted`, `demilestoned`, `edited`, `field_added`, `field_removed`, `labeled`, `locked`, `milestoned`, `opened`, `pinned`, `reopened`, `transferred`, `typed`, `unassigned`, `unlabeled`, `unlocked`, `unpinned`, `untyped`

An issue was assigned to a user.

#### Webhook payload object parameters

| Name       | Type             | Description                     |
| ---------- | ---------------- | ------------------------------- |
| `assignee` | `object or null` |                                 |
| `issue`    | `object`         | **Required.** The issue itself. |

## label

This event occurs when there is activity relating to labels. For more information, see "Managing labels." For information about the APIs to manage labels, see the GraphQL documentation or "Labels" in the REST API documentation.
If you want to receive an event when a label is added to or removed from an issue, pull request, or discussion, use the labeled or unlabeled action type for the issues, pull\_request, or discussion events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Metadata" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `archived`, `created`, `deleted`, `edited`, `unarchived`

A label was archived.

#### Webhook payload object parameters

| Name    | Type     | Description   |
| ------- | -------- | ------------- |
| `label` | `object` | **Required.** |

## marketplace\_purchase

This event occurs when there is activity relating to a GitHub Marketplace purchase. For more information, see "GitHub Marketplace." For information about the APIs to manage GitHub Marketplace listings, see the GraphQL documentation or "GitHub Marketplace" in the REST API documentation.

### Availability

* `marketplace`

### Webhook payload object

**Action type:** `cancelled`, `changed`, `pending_change`, `pending_change_cancelled`, `purchased`

Someone cancelled a GitHub Marketplace plan, and the last billing cycle has ended. The change will take effect on the account immediately.

#### Webhook payload object parameters

| Name                            | Type     | Description   |
| ------------------------------- | -------- | ------------- |
| `effective_date`                | `string` | **Required.** |
| `marketplace_purchase`          | `object` | **Required.** |
| `previous_marketplace_purchase` | `object` |               |

## member

This event occurs when there is activity relating to collaborators in a repository. For more information, see "Adding outside collaborators to repositories in your organization." For more information about the API to manage repository collaborators, see the GraphQL API documentation or "Collaborators" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Members" organization permission.

### Availability

* `business`
* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `added`, `edited`, `removed`

A GitHub user accepted an invitation to a repository.

#### Webhook payload object parameters

| Name      | Type             | Description   |
| --------- | ---------------- | ------------- |
| `changes` | `object`         |               |
| `member`  | `object or null` | **Required.** |

## membership

This event occurs when there is activity relating to team membership. For more information, see "About teams." For more information about the APIs to manage team memberships, see the GraphQL API documentation or "Team members" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Members" organization permission.

### Availability

* `organization`
* `business`
* `app`

### Webhook payload object

**Action type:** `added`, `removed`

An organization member was added to a team.

#### Webhook payload object parameters

| Name     | Type             | Description                                                                                    |
| -------- | ---------------- | ---------------------------------------------------------------------------------------------- |
| `member` | `object or null` | **Required.**                                                                                  |
| `scope`  | `string`         | **Required.** The scope of the membership. Currently, can only be team.                        |
| `team`   | `object`         | **Required.** Groups of organization members that gives permissions on specified repositories. |

## merge\_group

This event occurs when there is activity relating to a merge group in a merge queue. For more information, see "Managing a merge queue."
To subscribe to this event, a GitHub App must have at least read-level access for the "Merge queues" repository permission.

### Availability

* `app`

### Webhook payload object

**Action type:** `checks_requested`, `destroyed`

Status checks were requested for a merge group. This happens when a merge group is created or added to by the merge queue because a pull request was queued.
When you receive this event, you should perform checks on the head SHA and report status back using check runs or commit statuses.

#### Webhook payload object parameters

| Name          | Type     | Description                                                                                    |
| ------------- | -------- | ---------------------------------------------------------------------------------------------- |
| `merge_group` | `object` | **Required.** A group of pull requests that the merge queue has grouped together to be merged. |

## meta

This event occurs when there is activity relating to a webhook itself.
To subscribe to this event, a GitHub App must have at least read-level access for the "Meta" app permission.

### Availability

* `marketplace`
* `business`
* `repository`
* `organization`
* `app`

### Webhook payload object

The webhook was deleted.

#### Webhook payload object parameters

| Name      | Type      | Description                                                                                                                                                             |
| --------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hook`    | `object`  | **Required.** The deleted webhook. This will contain different keys based on the type of webhook it is: repository, organization, business, app, or GitHub Marketplace. |
| `hook_id` | `integer` | **Required.** The id of the modified webhook.                                                                                                                           |

## milestone

This event occurs when there is activity relating to milestones. For more information, see "About milestones." For information about the APIs to manage milestones, see the GraphQL documentation or "Milestones" in the REST API documentation.
If you want to receive an event when an issue or pull request is added to or removed from a milestone, use the milestoned or demilestoned action type for the issues or pull\_request events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Issues" or "Pull requests" repository permissions.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `closed`, `created`, `deleted`, `edited`, `opened`

A milestone was closed.

#### Webhook payload object parameters

| Name        | Type     | Description                                                     |
| ----------- | -------- | --------------------------------------------------------------- |
| `milestone` | `object` | **Required.** A collection of related issues and pull requests. |

## org\_block

This event occurs when organization owners or moderators block or unblock a non-member from collaborating on the organization's repositories. For more information, see "Blocking a user from your organization." For information about the APIs to manage blocked users, see the GraphQL documentation or "Blocking users" in the REST API documentation.
If you want to receive an event when members are added or removed from an organization, use the organization event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Administration" organization permission.

### Availability

* `organization`
* `business`
* `app`

### Webhook payload object

**Action type:** `blocked`, `unblocked`

A user was blocked from the organization.

#### Webhook payload object parameters

| Name           | Type             | Description   |
| -------------- | ---------------- | ------------- |
| `blocked_user` | `object or null` | **Required.** |

## organization

This event occurs when there is activity relating to an organization and its members. For more information, see "About organizations." For information about the APIs to manage organizations, see the GraphQL documentation or "Organizations" in the REST API documentation.
If you want to receive an event when a non-member is blocked or unblocked from an organization, use the org\_block event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Members" organization permission.

### Availability

* `organization`
* `business`
* `app`

### Webhook payload object

**Action type:** `deleted`, `member_added`, `member_invited`, `member_removed`, `renamed`

An organization was deleted.

#### Webhook payload object parameters

| Name         | Type     | Description                                                                                           |
| ------------ | -------- | ----------------------------------------------------------------------------------------------------- |
| `membership` | `object` | The membership between the user and the organization. Not present when the action is member\_invited. |

## package

This event occurs when there is activity relating to GitHub Packages. For more information, see "Introduction to GitHub Packages." For information about the APIs to manage GitHub Packages, see the GraphQL API documentation or "Packages" in the REST API documentation.

### Availability

* `repository`
* `organization`

### Webhook payload object

**Action type:** `published`, `updated`

A package was published to a registry.

#### Webhook payload object parameters

| Name      | Type     | Description                                  |
| --------- | -------- | -------------------------------------------- |
| `package` | `object` | **Required.** Information about the package. |

## page\_build

This event occurs when there is an attempted build of a GitHub Pages site. This event occurs regardless of whether the build is successful. For more information, see "Configuring a publishing source for your GitHub Pages site." For information about the API to manage GitHub Pages, see "Pages" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Pages" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name    | Type      | Description                                        |
| ------- | --------- | -------------------------------------------------- |
| `build` | `object`  | **Required.** The List GitHub Pages builds itself. |
| `id`    | `integer` | **Required.**                                      |

## personal\_access\_token\_request

This event occurs when there is activity relating to a request for a fine-grained personal access token to access resources that belong to a resource owner that requires approval for token access. For more information, see "Creating a personal access token."
To subscribe to this event, a GitHub App must have at least read-level access for the "Personal access token requests" organization permission.

### Availability

* `app`
* `organization`

### Webhook payload object

**Action type:** `approved`, `cancelled`, `created`, `denied`

A fine-grained personal access token request was approved.

#### Webhook payload object parameters

| Name                            | Type     | Description                                               |
| ------------------------------- | -------- | --------------------------------------------------------- |
| `personal_access_token_request` | `object` | **Required.** Details of a Personal Access Token Request. |

## ping

This event occurs when you create a new webhook. The ping event is a confirmation from GitHub that you configured the webhook correctly.

### Availability

* `repository`
* `organization`
* `app`
* `business`
* `marketplace`

### Webhook payload object

#### Webhook payload object parameters

| Name      | Type      | Description                                    |
| --------- | --------- | ---------------------------------------------- |
| `hook`    | `object`  | The webhook that is being pinged               |
| `hook_id` | `integer` | The ID of the webhook that triggered the ping. |
| `zen`     | `string`  | Random string of GitHub zen.                   |

## project

This event occurs when there is activity relating to a project (classic). For more information, see "About projects (classic)." For information about the API to manage classic projects, see the GraphQL API documentation or "Projects (classic)" in the REST API documentation.
For activity relating to a card or column on a project (classic), use the project\_card and project\_column event.
This event relates to projects (classic) only. For activity relating to the new Projects experience, use the projects\_v2 event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Projects" repository or organization permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `closed`, `created`, `deleted`, `edited`, `reopened`

A project (classic) was closed.

#### Webhook payload object parameters

| Name      | Type     | Description   |
| --------- | -------- | ------------- |
| `project` | `object` | **Required.** |

## project\_card

This event occurs when there is activity relating to a card on a project (classic). For more information, see "About projects (classic)." For information about the API to manage classic projects, see the GraphQL API documentation or "Projects (classic)" in the REST API documentation.
For activity relating to a project (classic) or a column on a project (classic), use the project and project\_column event.
This event relates to projects (classic) only. For activity relating to the new Projects experience, use the projects\_v2 event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Projects" repository or organization permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `converted`, `created`, `deleted`, `edited`, `moved`

A note in a project (classic) was converted to an issue.

#### Webhook payload object parameters

| Name           | Type     | Description   |
| -------------- | -------- | ------------- |
| `changes`      | `object` | **Required.** |
| `project_card` | `object` | **Required.** |

## project\_column

This event occurs when there is activity relating to a column on a project (classic). For more information, see "About projects (classic)." For information about the API to manage classic projects, see the GraphQL API documentation or "Projects (classic)" in the REST API documentation.
For activity relating to a project (classic) or a card on a project (classic), use the project and project\_card event.
This event relates to projects (classic) only. For activity relating to the new Projects experience, use the projects\_v2 event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Projects" repository or organization permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`, `moved`

A column was added to a project (classic).

#### Webhook payload object parameters

| Name             | Type     | Description   |
| ---------------- | -------- | ------------- |
| `project_column` | `object` | **Required.** |

## projects\_v2

This event occurs when there is activity relating to an organization-level project. For more information, see "About Projects." For information about the Projects API, see the GraphQL documentation.
For activity relating to a item on a project, use the projects\_v2\_item event. For activity relating to Projects (classic), use the project, project\_card, and project\_column events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Projects" organization permission.

Webhook events for projects are currently in public preview and subject to change. To share feedback about projects webhooks with GitHub, see the Projects webhook feedback discussion.

### Availability

* `organization`

### Webhook payload object

**Action type:** `closed`, `created`, `deleted`, `edited`, `reopened`

A project in the organization was closed.

#### Webhook payload object parameters

| Name          | Type     | Description                         |
| ------------- | -------- | ----------------------------------- |
| `projects_v2` | `object` | **Required.** A projects v2 project |

## projects\_v2\_item

This event occurs when there is activity relating to an item on an organization-level project. For more information, see "About Projects." For information about the Projects API, see the GraphQL documentation.
For activity relating to a project (instead of an item on a project), use the projects\_v2 event. For activity relating to Projects (classic), use the project, project\_card, and project\_column events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Projects" organization permission.

Webhook events for projects are currently in public preview and subject to change. To share feedback about projects webhooks with GitHub, see the Projects webhook feedback discussion.

### Availability

* `organization`

### Webhook payload object

**Action type:** `archived`, `converted`, `created`, `deleted`, `edited`, `reordered`, `restored`

An item on an organization project was archived. For more information, see "Archiving items from your project."

#### Webhook payload object parameters

| Name               | Type     | Description                                  |
| ------------------ | -------- | -------------------------------------------- |
| `changes`          | `object` | **Required.**                                |
| `projects_v2_item` | `object` | **Required.** An item belonging to a project |

## projects\_v2\_status\_update

This event occurs when there is activity relating to a status update on an organization-level project. For more information, see "About Projects."
For activity relating to a project, use the projects\_v2 event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Projects" organization permission.

To share feedback about projects webhooks with GitHub, see the Projects webhook feedback discussion.

### Availability

* `organization`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`

A status update was added to a project in the organization.

#### Webhook payload object parameters

| Name                        | Type     | Description                                           |
| --------------------------- | -------- | ----------------------------------------------------- |
| `projects_v2_status_update` | `object` | **Required.** An status update belonging to a project |

## public

This event occurs when repository visibility changes from private to public. For more information, see "Setting repository visibility."
To subscribe to this event, a GitHub App must have at least read-level access for the "Metadata" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

## pull\_request

This event occurs when there is activity on a pull request. For more information, see "About pull requests." For information about the APIs to manage pull requests, see the GraphQL API documentation or "Pulls" in the REST API documentation.
For activity related to pull request reviews, pull request review comments, pull request comments, or pull request review threads, use the pull\_request\_review, pull\_request\_review\_comment, issue\_comment, or pull\_request\_review\_thread events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Pull requests" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `assigned`, `auto_merge_disabled`, `auto_merge_enabled`, `closed`, `converted_to_draft`, `demilestoned`, `dequeued`, `edited`, `enqueued`, `labeled`, `locked`, `milestoned`, `opened`, `ready_for_review`, `reopened`, `review_request_removed`, `review_requested`, `stacked`, `synchronize`, `unassigned`, `unlabeled`, `unlocked`

A pull request was assigned to a user.

#### Webhook payload object parameters

| Name           | Type             | Description                            |
| -------------- | ---------------- | -------------------------------------- |
| `assignee`     | `object or null` | **Required.**                          |
| `number`       | `integer`        | **Required.** The pull request number. |
| `pull_request` | `object`         | **Required.**                          |

## pull\_request\_review

This event occurs when there is activity relating to a pull request review. A pull request review is a group of pull request review comments in addition to a body comment and a state. For more information, see "About pull request reviews." For information about the APIs to manage pull request reviews, see the GraphQL API documentation or "Pull request reviews" in the REST API documentation.
For activity related to pull request review comments, pull request comments, or pull request review threads, use the pull\_request\_review\_comment, issue\_comment, or pull\_request\_review\_thread events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Pull requests" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `dismissed`, `edited`, `submitted`

A review on a pull request was dismissed.

#### Webhook payload object parameters

| Name           | Type     | Description                                 |
| -------------- | -------- | ------------------------------------------- |
| `pull_request` | `object` | **Required.**                               |
| `review`       | `object` | **Required.** The review that was affected. |

## pull\_request\_review\_comment

This event occurs when there is activity relating to a pull request review comment. A pull request review comment is a comment on a pull request's diff. For more information, see "Commenting on a pull request." For information about the APIs to manage pull request review comments, see the GraphQL API documentation or "Pull request review comments" in the REST API documentation.
For activity related to pull request reviews, pull request comments, or pull request review threads, use the pull\_request\_review, issue\_comment, or pull\_request\_review\_thread events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Pull requests" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`

A comment on a pull request diff was created.

#### Webhook payload object parameters

| Name           | Type     | Description                       |
| -------------- | -------- | --------------------------------- |
| `comment`      | `object` | **Required.** The comment itself. |
| `pull_request` | `object` | **Required.**                     |

## pull\_request\_review\_thread

This event occurs when there is activity relating to a comment thread on a pull request. For more information, see "About pull request reviews." For information about the APIs to manage pull request reviews, see the GraphQL API documentation or "Pull request review comments" in the REST API documentation.
For activity related to pull request review comments, pull request comments, or pull request reviews, use the pull\_request\_review\_comment, issue\_comment, or pull\_request\_review events instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Pull requests" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `resolved`, `unresolved`

A comment thread on a pull request was marked as resolved.

#### Webhook payload object parameters

| Name           | Type             | Description   |
| -------------- | ---------------- | ------------- |
| `pull_request` | `object`         | **Required.** |
| `thread`       | `object`         | **Required.** |
| `updated_at`   | `string or null` |               |

## push

This event occurs when there is a push to a repository branch. This includes when a commit is pushed, when a commit tag is pushed,
when a branch is deleted, when a tag is deleted, or when a repository is created from a template. To subscribe to only branch
and tag deletions, use the delete webhook event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

Events will not be created if more than 5000 branches are pushed at once. Events will not be created for tags when more than three tags are pushed at once.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name          | Type               | Description                                                                                                                                                                                                                                                                                                                  |
| ------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `after`       | `string`           | **Required.** The SHA of the most recent commit on ref after the push.                                                                                                                                                                                                                                                       |
| `base_ref`    | `string or null`   | **Required.**                                                                                                                                                                                                                                                                                                                |
| `before`      | `string`           | **Required.** The SHA of the most recent commit on ref before the push.                                                                                                                                                                                                                                                      |
| `commits`     | `array of objects` | **Required.** An array of commit objects describing the pushed commits. (Pushed commits are all commits that are included in the compare between the before commit and the after commit.) The array includes a maximum of 2048 commits. If necessary, you can use the Commits API to fetch additional commits.               |
| `compare`     | `string`           | **Required.** URL that shows the changes in this ref update, from the before commit to the after commit. For a newly created ref that is directly based on the default branch, this is the comparison between the head of the default branch and the after commit. Otherwise, this shows all commits until the after commit. |
| `created`     | `boolean`          | **Required.** Whether this push created the ref.                                                                                                                                                                                                                                                                             |
| `deleted`     | `boolean`          | **Required.** Whether this push deleted the ref.                                                                                                                                                                                                                                                                             |
| `forced`      | `boolean`          | **Required.** Whether this push was a force push of the ref.                                                                                                                                                                                                                                                                 |
| `head_commit` | `object or null`   | **Required.**                                                                                                                                                                                                                                                                                                                |
| `pusher`      | `object`           | **Required.** Metaproperties for Git author/committer information.                                                                                                                                                                                                                                                           |
| `ref`         | `string`           | **Required.** The full git ref that was pushed. Example: refs/heads/main or refs/tags/v3.14.1.                                                                                                                                                                                                                               |

## registry\_package

This event occurs when there is activity relating to GitHub Packages. For more information, see "Introduction to GitHub Packages." For information about the APIs to manage GitHub Packages, see the GraphQL API documentation or "Packages" in the REST API documentation.
To install this event on a GitHub App, the app must have at least read-level access for the "Packages" repository permission.

GitHub recommends that you use the newer package event instead.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `published`, `updated`

A package was published to a registry.

#### Webhook payload object parameters

| Name               | Type     | Description   |
| ------------------ | -------- | ------------- |
| `registry_package` | `object` | **Required.** |

## release

This event occurs when there is activity relating to releases. For more information, see "About releases." For information about the APIs to manage releases, see the GraphQL API documentation or "Releases" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`, `prereleased`, `published`, `released`, `unpublished`

A draft was saved, or a release or pre-release was published without previously being saved as a draft.

#### Webhook payload object parameters

| Name      | Type     | Description                       |
| --------- | -------- | --------------------------------- |
| `release` | `object` | **Required.** The release object. |

## repository

This event occurs when there is activity relating to repositories. For more information, see "About repositories." For information about the APIs to manage repositories, see the GraphQL documentation or "Repositories" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Metadata" repository permission.

### Availability

* `business`
* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `archived`, `created`, `deleted`, `edited`, `privatized`, `publicized`, `renamed`, `transferred`, `unarchived`

A repository was archived.

## repository\_advisory

This event occurs when there is activity relating to a repository security advisory. For more information about repository security advisories, see "About GitHub Security Advisories for repositories."
To subscribe to this event, a GitHub App must have at least read-level access for the "Repository security advisories" permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `published`, `reported`

A repository security advisory was published.

#### Webhook payload object parameters

| Name                  | Type     | Description                                   |
| --------------------- | -------- | --------------------------------------------- |
| `repository_advisory` | `object` | **Required.** A repository security advisory. |

## repository\_dispatch

This event occurs when a GitHub App sends a POST request to /repos/{owner}/{repo}/dispatches. For more information, see the REST API documentation for creating a repository dispatch event. In the payload, the action will be the event\_type that was specified in the POST /repos/{owner}/{repo}/dispatches request body.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

### Availability

* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name             | Type             | Description                                                                                                     |
| ---------------- | ---------------- | --------------------------------------------------------------------------------------------------------------- |
| `branch`         | `string`         | **Required.**                                                                                                   |
| `client_payload` | `object or null` | **Required.** The client\_payload that was specified in the POST /repos/{owner}/{repo}/dispatches request body. |

## repository\_import

This event occurs when a repository is imported to GitHub. For more information, see "Importing a repository with GitHub Importer." For more information about the API to manage imports, see the REST API documentation.

### Availability

* `repository`
* `organization`

### Webhook payload object

#### Webhook payload object parameters

| Name     | Type     | Description   |
| -------- | -------- | ------------- |
| `status` | `string` | **Required.** |

## repository\_ruleset

This event occurs when there is activity relating to repository rulesets.
For more information about repository rulesets, see "Managing rulesets."
For more information on managing rulesets via the APIs, see Repository ruleset in the GraphQL documentation or "Repository rules" and "Organization rules in the REST API documentation."
To subscribe to this event, a GitHub App must have at least read-level access for the "Administration" repository or organization permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`, `edited`

A repository ruleset was created.

#### Webhook payload object parameters

| Name                 | Type     | Description                                                              |
| -------------------- | -------- | ------------------------------------------------------------------------ |
| `repository_ruleset` | `object` | **Required.** A set of rules to apply when specified conditions are met. |

## repository\_vulnerability\_alert

This event occurs when there is activity relating to a security vulnerability alert in a repository.

Closing down notice: This event is closing down. Use the dependabot\_alert event instead.

### Availability

* `repository`
* `organization`

### Webhook payload object

**Action type:** `create`, `dismiss`, `reopen`, `resolve`

A repository vulnerability alert was created.

#### Webhook payload object parameters

| Name    | Type     | Description                                                    |
| ------- | -------- | -------------------------------------------------------------- |
| `alert` | `object` | **Required.** The security alert of the vulnerable dependency. |

## secret\_scanning\_alert

This event occurs when there is activity relating to a secret scanning alert. For more information about secret scanning, see "About secret scanning." For information about the API to manage secret scanning alerts, see "Secret scanning" in the REST API documentation.
For activity relating to secret scanning alert locations, use the secret\_scanning\_alert\_location event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Secret scanning alerts" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `assigned`, `created`, `metadata_created`, `metadata_removed`, `publicly_leaked`, `reopened`, `resolved`, `unassigned`, `validated`

A secret scanning alert was assigned.

#### Webhook payload object parameters

| Name       | Type     | Description    |
| ---------- | -------- | -------------- |
| `alert`    | `object` | **Required.**  |
| `assignee` | `object` | A GitHub user. |

## secret\_scanning\_alert\_location

This event occurs when there is activity relating to the locations of a secret in a secret scanning alert.
For more information about secret scanning, see "About secret scanning." For information about the API to manage secret scanning alerts, see "Secret scanning" in the REST API documentation.
For activity relating to secret scanning alerts, use the secret\_scanning\_alert event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Secret scanning alerts" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

A new instance of a previously detected secret was detected in a repository, and the location of the secret was added to the existing alert.

#### Webhook payload object parameters

| Name       | Type     | Description   |
| ---------- | -------- | ------------- |
| `alert`    | `object` | **Required.** |
| `location` | `object` | **Required.** |

## secret\_scanning\_scan

This event occurs when secret scanning completes certain scans on a repository. For more information about secret scanning, see "About secret scanning."
Scans can originate from multiple events such as updates to a custom pattern, a push to a repository, or updates
to patterns from partners. For more information on custom patterns, see "About custom patterns."
To subscribe to this event, a GitHub App must have at least read-level access for the "Secret scanning alerts" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

A secret scanning scan was completed.

#### Webhook payload object parameters

| Name                   | Type                       | Description                                                                                                  |
| ---------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `type`                 | `string`                   | **Required.** What type of scan was completed                                                                |
| `source`               | `string`                   | **Required.** What type of content was scanned                                                               |
| `started_at`           | `string`                   | **Required.** The time that the alert was resolved in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.                 |
| `completed_at`         | `string`                   | **Required.** The time that the alert was resolved in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.                 |
| `secret_types`         | `array of strings or null` | List of patterns that were updated. This will be empty for normal backfill scans or custom pattern updates   |
| `custom_pattern_name`  | `string or null`           | If the scan was triggered by a custom pattern update, this will be the name of the pattern that was updated  |
| `custom_pattern_scope` | `string or null`           | If the scan was triggered by a custom pattern update, this will be the scope of the pattern that was updated |

## security\_advisory

This event occurs when there is activity relating to a global security advisory that was reviewed by GitHub. A GitHub-reviewed global security advisory provides information about security vulnerabilities or malware that have been mapped to packages in ecosystems we support. For more information about global security advisories, see "About global security advisories." For information about the API to manage security advisories, see the REST API documentation or the GraphQL documentation.
GitHub Dependabot alerts are also powered by the security advisory dataset. For more information, see "About Dependabot alerts."

### Availability

* `app`

### Webhook payload object

**Action type:** `published`, `updated`, `withdrawn`

A security advisory was published to the GitHub community.

#### Webhook payload object parameters

| Name                | Type     | Description                                                                                       |
| ------------------- | -------- | ------------------------------------------------------------------------------------------------- |
| `security_advisory` | `object` | **Required.** The details of the security advisory, including summary, description, and severity. |

## security\_and\_analysis

This event occurs when code security and analysis features are enabled or disabled for a repository. For more information, see "GitHub security features."
To subscribe to this event, a GitHub App must have at least read-level access for the "Administration" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name      | Type     | Description   |
| --------- | -------- | ------------- |
| `changes` | `object` | **Required.** |

## sponsorship

This event occurs when there is activity relating to a sponsorship listing. For more information, see "About GitHub Sponsors." For information about the API to manage sponsors, see the GraphQL documentation.
You can only create a sponsorship webhook on GitHub.com. For more information, see "Configuring webhooks for events in your sponsored account."

### Availability

* `sponsors_listing`

### Webhook payload object

**Action type:** `cancelled`, `created`, `edited`, `pending_cancellation`, `pending_tier_change`, `tier_changed`

A sponsorship was cancelled and the last billing cycle has ended.
This event is only sent when a recurring (monthly) sponsorship is cancelled; it is not sent for one-time sponsorships.

#### Webhook payload object parameters

| Name          | Type     | Description   |
| ------------- | -------- | ------------- |
| `sponsorship` | `object` | **Required.** |

## star

This event occurs when there is activity relating to repository stars. For more information about stars, see "Saving repositories with stars." For information about the APIs to manage stars, see the GraphQL documentation or "Starring" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Metadata" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `created`, `deleted`

Someone starred a repository.

#### Webhook payload object parameters

| Name         | Type             | Description                                                                                                                                     |
| ------------ | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `starred_at` | `string or null` | **Required.** The time the star was created. This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ. Will be null for the deleted action. |

## status

This event occurs when the status of a Git commit changes. For example, commits can be marked as error, failure, pending, or success. For more information, see "About status checks." For information about the APIs to manage commit statuses, see the GraphQL documentation or "Commit statuses" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Commit statuses" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name          | Type               | Description                                                                                                                                                                                                 |
| ------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `avatar_url`  | `string or null`   |                                                                                                                                                                                                             |
| `branches`    | `array of objects` | **Required.** An array of branch objects containing the status' SHA. Each branch contains the given SHA, but the SHA may or may not be the head of the branch. The array includes a maximum of 10 branches. |
| `commit`      | `object`           | **Required.**                                                                                                                                                                                               |
| `context`     | `string`           | **Required.**                                                                                                                                                                                               |
| `created_at`  | `string`           | **Required.**                                                                                                                                                                                               |
| `description` | `string or null`   | **Required.** The optional human-readable description added to the status.                                                                                                                                  |
| `id`          | `integer`          | **Required.** The unique identifier of the status.                                                                                                                                                          |
| `name`        | `string`           | **Required.**                                                                                                                                                                                               |
| `sha`         | `string`           | **Required.** The Commit SHA.                                                                                                                                                                               |
| `state`       | `string`           | **Required.** The new state. Can be pending, success, failure, or error.                                                                                                                                    |
| `target_url`  | `string or null`   | **Required.** The optional link added to the status.                                                                                                                                                        |
| `updated_at`  | `string`           | **Required.**                                                                                                                                                                                               |

## sub\_issues

This event occurs when there is activity relating to sub-issues.
For activity relating to issues more generally, use the issues event instead.
To subscribe to this event, a GitHub App must have at least read-level access for the "Issues" repository permissions.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `parent_issue_added`, `parent_issue_removed`, `sub_issue_added`, `sub_issue_removed`

A parent issue was added to an issue.

#### Webhook payload object parameters

| Name                | Type     | Description                                                                                            |
| ------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| `parent_issue_id`   | `number` | The ID of the parent issue.                                                                            |
| `parent_issue`      | `object` | Issues are a great way to keep track of tasks, enhancements, and bugs for your projects.               |
| `parent_issue_repo` | `object` | A repository on GitHub.                                                                                |
| `sub_issue_id`      | `number` | **Required.** The ID of the sub-issue.                                                                 |
| `sub_issue`         | `object` | **Required.** Issues are a great way to keep track of tasks, enhancements, and bugs for your projects. |

## team

This event occurs when there is activity relating to teams in an organization.
For more information, see "About teams."
To subscribe to this event, a GitHub App must have at least read-level access for the "Members" organization permission.

### Availability

* `organization`
* `business`
* `app`

### Webhook payload object

**Action type:** `added_to_repository`, `created`, `deleted`, `edited`, `removed_from_repository`

A team was granted access to a repository.

#### Webhook payload object parameters

| Name   | Type     | Description                                                                                    |
| ------ | -------- | ---------------------------------------------------------------------------------------------- |
| `team` | `object` | **Required.** Groups of organization members that gives permissions on specified repositories. |

## team\_add

This event occurs when a team is added to a repository.
For more information, see "Managing teams and people with access to your repository."
For activity relating to teams, see the teams event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Members" organization permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name   | Type     | Description                                                                                    |
| ------ | -------- | ---------------------------------------------------------------------------------------------- |
| `team` | `object` | **Required.** Groups of organization members that gives permissions on specified repositories. |

## watch

This event occurs when there is activity relating to watching, or subscribing to, a repository. For more information about watching, see "Managing your subscriptions." For information about the APIs to manage watching, see "Watching" in the REST API documentation.
To subscribe to this event, a GitHub App must have at least read-level access for the "Metadata" repository permission.

### Availability

* `repository`
* `organization`
* `app`

### Webhook payload object

Someone started watching the repository.

## workflow\_dispatch

This event occurs when a GitHub Actions workflow is manually triggered. For more information, see "Manually running a workflow."
For activity relating to workflow runs, use the workflow\_run event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Contents" repository permission.

### Availability

* `app`

### Webhook payload object

#### Webhook payload object parameters

| Name       | Type             | Description   |
| ---------- | ---------------- | ------------- |
| `inputs`   | `object or null` | **Required.** |
| `ref`      | `string`         | **Required.** |
| `workflow` | `string`         | **Required.** |

## workflow\_job

This event occurs when there is activity relating to a job in a GitHub Actions workflow. For more information, see "Using jobs in a workflow." For information about the API to manage workflow jobs, see "Workflow jobs" in the REST API documentation.
For activity relating to a workflow run instead of a job in a workflow run, use the workflow\_run event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Actions" repository permission.

### Availability

* `business`
* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `completed`, `in_progress`, `queued`, `waiting`

A job in a workflow run finished. This event occurs when a job in a workflow is completed, regardless of whether the job was successful or unsuccessful.

#### Webhook payload object parameters

| Name           | Type     | Description                                                 |
| -------------- | -------- | ----------------------------------------------------------- |
| `workflow_job` | `object` | **Required.**                                               |
| `deployment`   | `object` | A request for a specific ref(branch,sha,tag) to be deployed |

## workflow\_run

This event occurs when there is activity relating to a run of a GitHub Actions workflow. For more information, see "About workflows." For information about the APIs to manage workflow runs, see the GraphQL documentation or "Workflow runs" in the REST API documentation.
For activity relating to a job in a workflow run, use the workflow\_job event.
To subscribe to this event, a GitHub App must have at least read-level access for the "Actions" repository permission.

### Availability

* `business`
* `repository`
* `organization`
* `app`

### Webhook payload object

**Action type:** `completed`, `in_progress`, `requested`

A workflow run finished. This event occurs when a workflow run is completed, regardless of whether the workflow was successful or unsuccessful.

#### Webhook payload object parameters

| Name           | Type             | Description   |
| -------------- | ---------------- | ------------- |
| `workflow`     | `object or null` | **Required.** |
| `workflow_run` | `object`         | **Required.** |