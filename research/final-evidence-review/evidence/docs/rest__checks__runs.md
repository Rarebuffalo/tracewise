# REST API endpoints for check runs

Use the REST API to manage check runs.

> \[!NOTE]
> Write permission for the REST API to interact with checks is only available to GitHub Apps. OAuth apps and authenticated users can view check runs and check suites, but they are not able to create them. If you aren't building a GitHub App, you might be interested in using the REST API to interact with [commit statuses](/en/rest/commits#commit-statuses).

> \[!NOTE]
> Most endpoints use `Authorization: Bearer <YOUR-TOKEN>` and `Accept: application/vnd.github+json` headers, plus `X-GitHub-Api-Version: 2026-03-10`. Curl examples below omit these standard headers for brevity.

## Create a check run

```
POST /repos/{owner}/{repo}/check-runs
```

Creates a new check run for a specific commit in a repository.
To create a check run, you must use a GitHub App. OAuth apps and authenticated users are not able to create a check suite.
In a check suite, GitHub limits the number of check runs with the same name to 1000. Once these check runs exceed 1000, GitHub will start to automatically delete older check runs.
Note

The Checks API only looks for pushes in the repository where the check suite or check run were created. Pushes to a branch in a forked repository are not detected and return an empty pull\_requests array.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

#### Body parameters

* **`status`** (string) (required)
  Can be one of: `completed`

### HTTP response status codes

* **201** - Created

### Code examples

#### Example of an in\_progress conclusion

**Request:**

```curl
curl -L \
  -X POST \
  https://api.github.com/repos/OWNER/REPO/check-runs \
  -d '{
  "name": "mighty_readme",
  "head_sha": "ce587453ced02b1526dfb4cb910479d431683101",
  "status": "in_progress",
  "external_id": "42",
  "started_at": "2018-05-04T01:14:52Z",
  "output": {
    "title": "Mighty Readme report",
    "summary": "",
    "text": ""
  }
}'
```

**Response schema (Status: 201):**

* `id`: required, integer, format: int64
* `head_sha`: required, string
* `node_id`: required, string
* `external_id`: required, string or null
* `url`: required, string
* `html_url`: required, string or null
* `details_url`: required, string or null
* `status`: required, string, enum: `queued`, `in_progress`, `completed`, `waiting`, `requested`, `pending`
* `conclusion`: required, string or null, enum: `success`, `failure`, `neutral`, `cancelled`, `skipped`, `timed_out`, `action_required`, `null`
* `started_at`: required, string or null, format: date-time
* `completed_at`: required, string or null, format: date-time
* `output`: required, object:
  * `title`: required, string or null
  * `summary`: required, string or null
  * `text`: required, string or null
  * `annotations_count`: required, integer
  * `annotations_url`: required, string, format: uri
* `name`: required, string
* `check_suite`: required, object or null:
  * `id`: required, integer
* `app`: required, any of:
  * **null**
  * **GitHub app**
    * `id`: required, integer
    * `slug`: string
    * `node_id`: required, string
    * `client_id`: string
    * `owner`: required, one of:
      * **Simple User**
        * `name`: string or null
        * `email`: string or null
        * `login`: required, string
        * `id`: required, integer, format: int64
        * `node_id`: required, string
        * `avatar_url`: required, string, format: uri
        * `gravatar_id`: required, string or null
        * `url`: required, string, format: uri
        * `html_url`: required, string, format: uri
        * `followers_url`: required, string, format: uri
        * `following_url`: required, string
        * `gists_url`: required, string
        * `starred_url`: required, string
        * `subscriptions_url`: required, string, format: uri
        * `organizations_url`: required, string, format: uri
        * `repos_url`: required, string, format: uri
        * `events_url`: required, string
        * `received_events_url`: required, string, format: uri
        * `type`: required, string
        * `site_admin`: required, boolean
        * `starred_at`: string
        * `user_view_type`: string
      * **Enterprise**
        * `description`: string or null
        * `html_url`: required, string, format: uri
        * `website_url`: string or null, format: uri
        * `id`: required, integer
        * `node_id`: required, string
        * `name`: required, string
        * `slug`: required, string
        * `created_at`: required, string or null, format: date-time
        * `updated_at`: required, string or null, format: date-time
        * `avatar_url`: required, string, format: uri
    * `name`: required, string
    * `description`: required, string or null
    * `external_url`: required, string, format: uri
    * `html_url`: required, string, format: uri
    * `created_at`: required, string, format: date-time
    * `updated_at`: required, string, format: date-time
    * `permissions`: required, object, additional properties: string:
      * `issues`: string
      * `checks`: string
      * `metadata`: string
      * `contents`: string
      * `deployments`: string
    * `events`: required, array of string
    * `installations_count`: integer
* `pull_requests`: required, array of `Pull Request Minimal`:
  * `id`: required, integer, format: int64
  * `number`: required, integer
  * `url`: required, string
  * `head`: required, object:
    * `ref`: required, string
    * `sha`: required, string
    * `repo`: required, object:
      * `id`: required, integer, format: int64
      * `url`: required, string
      * `name`: required, string
  * `base`: required, object:
    * `ref`: required, string
    * `sha`: required, string
    * `repo`: required, object:
      * `id`: required, integer, format: int64
      * `url`: required, string
      * `name`: required, string
* `deployment`: `Deployment`:
  * `url`: required, string, format: uri
  * `id`: required, integer
  * `node_id`: required, string
  * `task`: required, string
  * `original_environment`: string
  * `environment`: required, string
  * `description`: required, string or null
  * `created_at`: required, string, format: date-time
  * `updated_at`: required, string, format: date-time
  * `statuses_url`: required, string, format: uri
  * `repository_url`: required, string, format: uri
  * `transient_environment`: boolean
  * `production_environment`: boolean
  * `performed_via_github_app`: any of:
    * **null**
    * **GitHub app** (see above)

#### Example of a completed conclusion

**Request:**

```curl
curl -L \
  -X POST \
  https://api.github.com/repos/OWNER/REPO/check-runs \
  -d '{
  "name": "mighty_readme",
  "head_sha": "ce587453ced02b1526dfb4cb910479d431683101",
  "status": "completed",
  "started_at": "2017-11-30T19:39:10Z",
  "conclusion": "success",
  "completed_at": "2017-11-30T19:49:10Z",
  "output": {
    "title": "Mighty Readme report",
    "summary": "There are 0 failures, 2 warnings, and 1 notices.",
    "text": "You may have some misspelled words on lines 2 and 4. You also may want to add a section in your README about how to install your app.",
    "annotations": [
      {
        "path": "README.md",
        "annotation_level": "warning",
        "title": "Spell Checker",
        "message": "Check your spelling for '\''banaas'\''.",
        "raw_details": "Do you mean '\''bananas'\'' or '\''banana'\''?",
        "start_line": 2,
        "end_line": 2
      },
      {
        "path": "README.md",
        "annotation_level": "warning",
        "title": "Spell Checker",
        "message": "Check your spelling for '\''aples'\''",
        "raw_details": "Do you mean '\''apples'\'' or '\''Naples'\''",
        "start_line": 4,
        "end_line": 4
      }
    ],
    "images": [
      {
        "alt": "Super bananas",
        "image_url": "http://example.com/images/42"
      }
    ]
  },
  "actions": [
    {
      "label": "Fix",
      "identifier": "fix_errors",
      "description": "Allow us to fix these errors for you"
    }
  ]
}'
```

**Response schema (Status: 201):**

* `id`: required, integer, format: int64
* `head_sha`: required, string
* `node_id`: required, string
* `external_id`: required, string or null
* `url`: required, string
* `html_url`: required, string or null
* `details_url`: required, string or null
* `status`: required, string, enum: `queued`, `in_progress`, `completed`, `waiting`, `requested`, `pending`
* `conclusion`: required, string or null, enum: `success`, `failure`, `neutral`, `cancelled`, `skipped`, `timed_out`, `action_required`, `null`
* `started_at`: required, string or null, format: date-time
* `completed_at`: required, string or null, format: date-time
* `output`: required, object:
  * `title`: required, string or null
  * `summary`: required, string or null
  * `text`: required, string or null
  * `annotations_count`: required, integer
  * `annotations_url`: required, string, format: uri
* `name`: required, string
* `check_suite`: required, object or null:
  * `id`: required, integer
* `app`: required, any of:
  * **null**
  * **GitHub app**
    * `id`: required, integer
    * `slug`: string
    * `node_id`: required, string
    * `client_id`: string
    * `owner`: required, one of:
      * **Simple User**
        * `name`: string or null
        * `email`: string or null
        * `login`: required, string
        * `id`: required, integer, format: int64
        * `node_id`: required, string
        * `avatar_url`: required, string, format: uri
        * `gravatar_id`: required, string or null
        * `url`: required, string, format: uri
        * `html_url`: required, string, format: uri
        * `followers_url`: required, string, format: uri
        * `following_url`: required, string
        * `gists_url`: required, string
        * `starred_url`: required, string
        * `subscriptions_url`: required, string, format: uri
        * `organizations_url`: required, string, format: uri
        * `repos_url`: required, string, format: uri
        * `events_url`: required, string
        * `received_events_url`: required, string, format: uri
        * `type`: required, string
        * `site_admin`: required, boolean
        * `starred_at`: string
        * `user_view_type`: string
      * **Enterprise**
        * `description`: string or null
        * `html_url`: required, string, format: uri
        * `website_url`: string or null, format: uri
        * `id`: required, integer
        * `node_id`: required, string
        * `name`: required, string
        * `slug`: required, string
        * `created_at`: required, string or null, format: date-time
        * `updated_at`: required, string or null, format: date-time
        * `avatar_url`: required, string, format: uri
    * `name`: required, string
    * `description`: required, string or null
    * `external_url`: required, string, format: uri
    * `html_url`: required, string, format: uri
    * `created_at`: required, string, format: date-time
    * `updated_at`: required, string, format: date-time
    * `permissions`: required, object, additional properties: string:
      * `issues`: string
      * `checks`: string
      * `metadata`: string
      * `contents`: string
      * `deployments`: string
    * `events`: required, array of string
    * `installations_count`: integer
* `pull_requests`: required, array of `Pull Request Minimal`:
  * `id`: required, integer, format: int64
  * `number`: required, integer
  * `url`: required, string
  * `head`: required, object:
    * `ref`: required, string
    * `sha`: required, string
    * `repo`: required, object:
      * `id`: required, integer, format: int64
      * `url`: required, string
      * `name`: required, string
  * `base`: required, object:
    * `ref`: required, string
    * `sha`: required, string
    * `repo`: required, object:
      * `id`: required, integer, format: int64
      * `url`: required, string
      * `name`: required, string
* `deployment`: `Deployment`:
  * `url`: required, string, format: uri
  * `id`: required, integer
  * `node_id`: required, string
  * `task`: required, string
  * `original_environment`: string
  * `environment`: required, string
  * `description`: required, string or null
  * `created_at`: required, string, format: date-time
  * `updated_at`: required, string, format: date-time
  * `statuses_url`: required, string, format: uri
  * `repository_url`: required, string, format: uri
  * `transient_environment`: boolean
  * `production_environment`: boolean
  * `performed_via_github_app`: any of:
    * **null**
    * **GitHub app** (see above)

## Get a check run

```
GET /repos/{owner}/{repo}/check-runs/{check_run_id}
```

Gets a single check run using its id.
Note

The Checks API only looks for pushes in the repository where the check suite or check run were created. Pushes to a branch in a forked repository are not detected and return an empty pull\_requests array.

OAuth app tokens and personal access tokens (classic) need the repo scope to use this endpoint on a private repository.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`check_run_id`** (integer) (required)
  The unique identifier of the check run.

### HTTP response status codes

* **200** - OK

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/repos/OWNER/REPO/check-runs/CHECK_RUN_ID
```

**Response schema (Status: 200):**

Same response schema as [Create a check run](#create-a-check-run).

## Update a check run

```
PATCH /repos/{owner}/{repo}/check-runs/{check_run_id}
```

Updates a check run for a specific commit in a repository.
Note

The endpoints to manage checks only look for pushes in the repository where the check suite or check run were created. Pushes to a branch in a forked repository are not detected and return an empty pull\_requests array.

OAuth apps and personal access tokens (classic) cannot use this endpoint.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`check_run_id`** (integer) (required)
  The unique identifier of the check run.

#### Body parameters

* **`name`** (string)
  The name of the check. For example, "code-coverage".

* **`details_url`** (string)
  The URL of the integrator's site that has the full details of the check.

* **`external_id`** (string)
  A reference for the run on the integrator's system.

* **`started_at`** (string)
  This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.

* **`status`** (string)
  The current status of the check run. Only GitHub Actions can set a status of waiting, pending, or requested.
  Can be one of: `queued`, `in_progress`, `completed`, `waiting`, `requested`, `pending`

* **`conclusion`** (string)
  Required if you provide completed\_at or a status of completed. The final conclusion of the check.
  Note: Providing conclusion will automatically set the status parameter to completed. You cannot change a check run conclusion to stale, only GitHub can set this.
  Can be one of: `action_required`, `cancelled`, `failure`, `neutral`, `success`, `skipped`, `stale`, `timed_out`

* **`completed_at`** (string)
  The time the check completed. This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.

* **`output`** (object)
  Check runs can accept a variety of data in the output object, including a title and summary and can optionally provide descriptive details about the run.
  * **`title`** (string)
    Required.
  * **`summary`** (string) (required)
    Can contain Markdown.
  * **`text`** (string)
    Can contain Markdown.
  * **`annotations`** (array of objects)
    Adds information from your analysis to specific lines of code. Annotations are visible in GitHub's pull request UI. Annotations are visible in GitHub's pull request UI. The Checks API limits the number of annotations to a maximum of 50 per API request. To create more than 50 annotations, you have to make multiple requests to the Update a check run endpoint. Each time you update the check run, annotations are appended to the list of annotations that already exist for the check run. GitHub Actions are limited to 10 warning annotations and 10 error annotations per step. For details about annotations in the UI, see "About status checks".
    * **`path`** (string) (required)
      The path of the file to add an annotation to. For example, assets/css/main.css.
    * **`start_line`** (integer) (required)
      The start line of the annotation. Line numbers start at 1.
    * **`end_line`** (integer) (required)
      The end line of the annotation.
    * **`start_column`** (integer)
      The start column of the annotation. Annotations only support start\_column and end\_column on the same line. Omit this parameter if start\_line and end\_line have different values. Column numbers start at 1.
    * **`end_column`** (integer)
      The end column of the annotation. Annotations only support start\_column and end\_column on the same line. Omit this parameter if start\_line and end\_line have different values.
    * **`annotation_level`** (string) (required)
      The level of the annotation.
      Can be one of: `notice`, `warning`, `failure`
    * **`message`** (string) (required)
      A short description of the feedback for these lines of code. The maximum size is 64 KB.
    * **`title`** (string)
      The title that represents the annotation. The maximum size is 255 characters.
    * **`raw_details`** (string)
      Details about this annotation. The maximum size is 64 KB.
  * **`images`** (array of objects)
    Adds images to the output displayed in the GitHub pull request UI.
    * **`alt`** (string) (required)
      The alternative text for the image.
    * **`image_url`** (string) (required)
      The full URL of the image.
    * **`caption`** (string)
      A short image description.

* **`actions`** (array of objects)
  Possible further actions the integrator can perform, which a user may trigger. Each action includes a label, identifier and description. A maximum of three actions are accepted. To learn more about check runs and requested actions, see "Check runs and requested actions."
  * **`label`** (string) (required)
    The text to be displayed on a button in the web UI. The maximum size is 20 characters.
  * **`description`** (string) (required)
    A short explanation of what this action would do. The maximum size is 40 characters.
  * **`identifier`** (string) (required)
    A reference for the action on the integrator's system. The maximum size is 20 characters.

### HTTP response status codes

* **200** - OK

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X PATCH \
  https://api.github.com/repos/OWNER/REPO/check-runs/CHECK_RUN_ID \
  -d '{
  "name": "mighty_readme",
  "started_at": "2018-05-04T01:14:52Z",
  "status": "completed",
  "conclusion": "success",
  "completed_at": "2018-05-04T01:14:52Z",
  "output": {
    "title": "Mighty Readme report",
    "summary": "There are 0 failures, 2 warnings, and 1 notices.",
    "text": "You may have some misspelled words on lines 2 and 4. You also may want to add a section in your README about how to install your app.",
    "annotations": [
      {
        "path": "README.md",
        "annotation_level": "warning",
        "title": "Spell Checker",
        "message": "Check your spelling for '\''banaas'\''.",
        "raw_details": "Do you mean '\''bananas'\'' or '\''banana'\''?",
        "start_line": 2,
        "end_line": 2
      },
      {
        "path": "README.md",
        "annotation_level": "warning",
        "title": "Spell Checker",
        "message": "Check your spelling for '\''aples'\''",
        "raw_details": "Do you mean '\''apples'\'' or '\''Naples'\''",
        "start_line": 4,
        "end_line": 4
      }
    ],
    "images": [
      {
        "alt": "Super bananas",
        "image_url": "http://example.com/images/42"
      }
    ]
  }
}'
```

**Response schema (Status: 200):**

Same response schema as [Create a check run](#create-a-check-run).

## List check run annotations

```
GET /repos/{owner}/{repo}/check-runs/{check_run_id}/annotations
```

Lists annotations for a check run using the annotation id.
OAuth app tokens and personal access tokens (classic) need the repo scope to use this endpoint on a private repository.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`check_run_id`** (integer) (required)
  The unique identifier of the check run.

* **`per_page`** (integer)
  The number of results per page (max 100). For more information, see "Using pagination in the REST API."
  Default: `30`

* **`page`** (integer)
  The page number of the results to fetch. For more information, see "Using pagination in the REST API."
  Default: `1`

### HTTP response status codes

* **200** - OK

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/repos/OWNER/REPO/check-runs/CHECK_RUN_ID/annotations
```

**Response schema (Status: 200):**

Array of `Check Annotation`:

* `path`: required, string
* `start_line`: required, integer
* `end_line`: required, integer
* `start_column`: required, integer or null
* `end_column`: required, integer or null
* `annotation_level`: required, string or null
* `title`: required, string or null
* `message`: required, string or null
* `raw_details`: required, string or null
* `blob_href`: required, string

## Rerequest a check run

```
POST /repos/{owner}/{repo}/check-runs/{check_run_id}/rerequest
```

Triggers GitHub to rerequest an existing check run, without pushing new code to a repository. This endpoint will trigger the check\_run webhook event with the action rerequested. When a check run is rerequested, the status of the check suite it belongs to is reset to queued and the conclusion is cleared. The check run itself is not updated. GitHub apps recieving the check\_run webhook with the rerequested action should then decide if the check run should be reset or updated and call the update check\_run endpoint to update the check\_run if desired.
For more information about how to re-run GitHub Actions jobs, see "Re-run a job from a workflow run".

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`check_run_id`** (integer) (required)
  The unique identifier of the check run.

### HTTP response status codes

* **201** - Created

* **403** - Forbidden if the check run is not rerequestable or doesn't belong to the authenticated GitHub App

* **404** - Resource not found

* **422** - Validation error if the check run is not rerequestable

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X POST \
  https://api.github.com/repos/OWNER/REPO/check-runs/CHECK_RUN_ID/rerequest
```

**Response schema (Status: 201):**

## List check runs in a check suite

```
GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs
```

Lists check runs for a check suite using its id.
Note

The endpoints to manage checks only look for pushes in the repository where the check suite or check run were created. Pushes to a branch in a forked repository are not detected and return an empty pull\_requests array.

OAuth app tokens and personal access tokens (classic) need the repo scope to use this endpoint on a private repository.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`check_suite_id`** (integer) (required)
  The unique identifier of the check suite.

* **`check_name`** (string)
  Returns check runs with the specified name.

* **`status`** (string)
  Returns check runs with the specified status.
  Can be one of: `queued`, `in_progress`, `completed`

* **`filter`** (string)
  Filters check runs by their completed\_at timestamp. latest returns the most recent check runs.
  Default: `latest`
  Can be one of: `latest`, `all`

* **`per_page`** (integer)
  The number of results per page (max 100). For more information, see "Using pagination in the REST API."
  Default: `30`

* **`page`** (integer)
  The page number of the results to fetch. For more information, see "Using pagination in the REST API."
  Default: `1`

### HTTP response status codes

* **200** - OK

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/repos/OWNER/REPO/check-suites/CHECK_SUITE_ID/check-runs
```

**Response schema (Status: 200):**

* `total_count`: required, integer
* `check_runs`: required, array of `CheckRun`:
  * `id`: required, integer, format: int64
  * `head_sha`: required, string
  * `node_id`: required, string
  * `external_id`: required, string or null
  * `url`: required, string
  * `html_url`: required, string or null
  * `details_url`: required, string or null
  * `status`: required, string, enum: `queued`, `in_progress`, `completed`, `waiting`, `requested`, `pending`
  * `conclusion`: required, string or null, enum: `success`, `failure`, `neutral`, `cancelled`, `skipped`, `timed_out`, `action_required`, `null`
  * `started_at`: required, string or null, format: date-time
  * `completed_at`: required, string or null, format: date-time
  * `output`: required, object:
    * `title`: required, string or null
    * `summary`: required, string or null
    * `text`: required, string or null
    * `annotations_count`: required, integer
    * `annotations_url`: required, string, format: uri
  * `name`: required, string
  * `check_suite`: required, object or null:
    * `id`: required, integer
  * `app`: required, any of:
    * **null**
    * **GitHub app**
      * `id`: required, integer
      * `slug`: string
      * `node_id`: required, string
      * `client_id`: string
      * `owner`: required, one of:
        * **Simple User**
          * `name`: string or null
          * `email`: string or null
          * `login`: required, string
          * `id`: required, integer, format: int64
          * `node_id`: required, string
          * `avatar_url`: required, string, format: uri
          * `gravatar_id`: required, string or null
          * `url`: required, string, format: uri
          * `html_url`: required, string, format: uri
          * `followers_url`: required, string, format: uri
          * `following_url`: required, string
          * `gists_url`: required, string
          * `starred_url`: required, string
          * `subscriptions_url`: required, string, format: uri
          * `organizations_url`: required, string, format: uri
          * `repos_url`: required, string, format: uri
          * `events_url`: required, string
          * `received_events_url`: required, string, format: uri
          * `type`: required, string
          * `site_admin`: required, boolean
          * `starred_at`: string
          * `user_view_type`: string
        * **Enterprise**
          * `description`: string or null
          * `html_url`: required, string, format: uri
          * `website_url`: string or null, format: uri
          * `id`: required, integer
          * `node_id`: required, string
          * `name`: required, string
          * `slug`: required, string
          * `created_at`: required, string or null, format: date-time
          * `updated_at`: required, string or null, format: date-time
          * `avatar_url`: required, string, format: uri
      * `name`: required, string
      * `description`: required, string or null
      * `external_url`: required, string, format: uri
      * `html_url`: required, string, format: uri
      * `created_at`: required, string, format: date-time
      * `updated_at`: required, string, format: date-time
      * `permissions`: required, object, additional properties: string:
        * `issues`: string
        * `checks`: string
        * `metadata`: string
        * `contents`: string
        * `deployments`: string
      * `events`: required, array of string
      * `installations_count`: integer
  * `pull_requests`: required, array of `Pull Request Minimal`:
    * `id`: required, integer, format: int64
    * `number`: required, integer
    * `url`: required, string
    * `head`: required, object:
      * `ref`: required, string
      * `sha`: required, string
      * `repo`: required, object:
        * `id`: required, integer, format: int64
        * `url`: required, string
        * `name`: required, string
    * `base`: required, object:
      * `ref`: required, string
      * `sha`: required, string
      * `repo`: required, object:
        * `id`: required, integer, format: int64
        * `url`: required, string
        * `name`: required, string
  * `deployment`: `Deployment`:
    * `url`: required, string, format: uri
    * `id`: required, integer
    * `node_id`: required, string
    * `task`: required, string
    * `original_environment`: string
    * `environment`: required, string
    * `description`: required, string or null
    * `created_at`: required, string, format: date-time
    * `updated_at`: required, string, format: date-time
    * `statuses_url`: required, string, format: uri
    * `repository_url`: required, string, format: uri
    * `transient_environment`: boolean
    * `production_environment`: boolean
    * `performed_via_github_app`: any of:
      * **null**
      * **GitHub app** (see above)

## List check runs for a Git reference

```
GET /repos/{owner}/{repo}/commits/{ref}/check-runs
```

Lists check runs for a commit ref. The ref can be a SHA, branch name, or a tag name.
Note

The endpoints to manage checks only look for pushes in the repository where the check suite or check run were created. Pushes to a branch in a forked repository are not detected and return an empty pull\_requests array.

If there are more than 1000 check suites on a single git reference, this endpoint will limit check runs to the 1000 most recent check suites. To iterate over all possible check runs, use the List check suites for a Git reference endpoint and provide the check\_suite\_id parameter to the List check runs in a check suite endpoint.
OAuth app tokens and personal access tokens (classic) need the repo scope to use this endpoint on a private repository.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`ref`** (string) (required)
  The commit reference. Can be a commit SHA, branch name (heads/BRANCH\_NAME), or tag name (tags/TAG\_NAME). For more information, see "Git References" in the Git documentation.

* **`check_name`** (string)
  Returns check runs with the specified name.

* **`status`** (string)
  Returns check runs with the specified status.
  Can be one of: `queued`, `in_progress`, `completed`

* **`filter`** (string)
  Filters check runs by their completed\_at timestamp. latest returns the most recent check runs.
  Default: `latest`
  Can be one of: `latest`, `all`

* **`per_page`** (integer)
  The number of results per page (max 100). For more information, see "Using pagination in the REST API."
  Default: `30`

* **`page`** (integer)
  The page number of the results to fetch. For more information, see "Using pagination in the REST API."
  Default: `1`

* **`app_id`** (integer)

### HTTP response status codes

* **200** - OK

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/repos/OWNER/REPO/commits/REF/check-runs
```

**Response schema (Status: 200):**

Same response schema as [List check runs in a check suite](#list-check-runs-in-a-check-suite).