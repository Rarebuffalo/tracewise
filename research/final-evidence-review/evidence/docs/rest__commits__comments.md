# REST API endpoints for commit comments

Use the REST API to interact with commit comments.

## About commit comments

You can create, edit, and view commit comments using the REST API. A commit comment is a comment made on a specific commit. For more information, see [Working with comments](/en/rest/guides/working-with-comments#commit-comments).

> \[!NOTE]
> Most endpoints use `Authorization: Bearer <YOUR-TOKEN>` and `Accept: application/vnd.github+json` headers, plus `X-GitHub-Api-Version: 2026-03-10`. Curl examples below omit these standard headers for brevity.

## List commit comments for a repository

```
GET /repos/{owner}/{repo}/comments
```

Lists the commit comments for a specified repository. Comments are ordered by ascending ID.
This endpoint supports the following custom media types. For more information, see "Media types."

application/vnd.github-commitcomment.raw+json: Returns the raw markdown body. Response will include body. This is the default if you do not pass any specific media type.
application/vnd.github-commitcomment.text+json: Returns a text only representation of the markdown body. Response will include body\_text.
application/vnd.github-commitcomment.html+json: Returns HTML rendered from the body's markdown. Response will include body\_html.
application/vnd.github-commitcomment.full+json: Returns raw, text, and HTML representations. Response will include body, body\_text, and body\_html.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

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
  https://api.github.com/repos/OWNER/REPO/comments
```

**Response schema (Status: 200):**

Array of `Commit Comment`:

* `html_url`: required, string, format: uri
* `url`: required, string, format: uri
* `id`: required, integer
* `node_id`: required, string
* `body`: required, string
* `path`: required, string or null
* `position`: required, integer or null
* `line`: required, integer or null
* `commit_id`: required, string
* `user`: required, any of:
  * **null**
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
* `created_at`: required, string, format: date-time
* `updated_at`: required, string, format: date-time
* `author_association`: required, string, enum: `COLLABORATOR`, `CONTRIBUTOR`, `FIRST_TIMER`, `FIRST_TIME_CONTRIBUTOR`, `MANNEQUIN`, `MEMBER`, `NONE`, `OWNER`
* `reactions`: `Reaction Rollup`:
  * `url`: required, string, format: uri
  * `total_count`: required, integer
  * `+1`: required, integer
  * `-1`: required, integer
  * `laugh`: required, integer
  * `confused`: required, integer
  * `heart`: required, integer
  * `hooray`: required, integer
  * `eyes`: required, integer
  * `rocket`: required, integer

## Get a commit comment

```
GET /repos/{owner}/{repo}/comments/{comment_id}
```

Gets a specified commit comment.
This endpoint supports the following custom media types. For more information, see "Media types."

application/vnd.github-commitcomment.raw+json: Returns the raw markdown body. Response will include body. This is the default if you do not pass any specific media type.
application/vnd.github-commitcomment.text+json: Returns a text only representation of the markdown body. Response will include body\_text.
application/vnd.github-commitcomment.html+json: Returns HTML rendered from the body's markdown. Response will include body\_html.
application/vnd.github-commitcomment.full+json: Returns raw, text, and HTML representations. Response will include body, body\_text, and body\_html.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`comment_id`** (integer) (required)
  The unique identifier of the comment.

### HTTP response status codes

* **200** - OK

* **404** - Resource not found

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/repos/OWNER/REPO/comments/COMMENT_ID
```

**Response schema (Status: 200):**

* `html_url`: required, string, format: uri
* `url`: required, string, format: uri
* `id`: required, integer
* `node_id`: required, string
* `body`: required, string
* `path`: required, string or null
* `position`: required, integer or null
* `line`: required, integer or null
* `commit_id`: required, string
* `user`: required, any of:
  * **null**
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
* `created_at`: required, string, format: date-time
* `updated_at`: required, string, format: date-time
* `author_association`: required, string, enum: `COLLABORATOR`, `CONTRIBUTOR`, `FIRST_TIMER`, `FIRST_TIME_CONTRIBUTOR`, `MANNEQUIN`, `MEMBER`, `NONE`, `OWNER`
* `reactions`: `Reaction Rollup`:
  * `url`: required, string, format: uri
  * `total_count`: required, integer
  * `+1`: required, integer
  * `-1`: required, integer
  * `laugh`: required, integer
  * `confused`: required, integer
  * `heart`: required, integer
  * `hooray`: required, integer
  * `eyes`: required, integer
  * `rocket`: required, integer

## Update a commit comment

```
PATCH /repos/{owner}/{repo}/comments/{comment_id}
```

Updates the contents of a specified commit comment.
This endpoint supports the following custom media types. For more information, see "Media types."

application/vnd.github-commitcomment.raw+json: Returns the raw markdown body. Response will include body. This is the default if you do not pass any specific media type.
application/vnd.github-commitcomment.text+json: Returns a text only representation of the markdown body. Response will include body\_text.
application/vnd.github-commitcomment.html+json: Returns HTML rendered from the body's markdown. Response will include body\_html.
application/vnd.github-commitcomment.full+json: Returns raw, text, and HTML representations. Response will include body, body\_text, and body\_html.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`comment_id`** (integer) (required)
  The unique identifier of the comment.

#### Body parameters

* **`body`** (string) (required)
  The contents of the comment

### HTTP response status codes

* **200** - OK

* **404** - Resource not found

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X PATCH \
  https://api.github.com/repos/OWNER/REPO/comments/COMMENT_ID \
  -d '{
  "body": "Nice change"
}'
```

**Response schema (Status: 200):**

Same response schema as [Get a commit comment](#get-a-commit-comment).

## Delete a commit comment

```
DELETE /repos/{owner}/{repo}/comments/{comment_id}
```

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`comment_id`** (integer) (required)
  The unique identifier of the comment.

### HTTP response status codes

* **204** - No Content

* **404** - Resource not found

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X DELETE \
  https://api.github.com/repos/OWNER/REPO/comments/COMMENT_ID
```

**Response schema (Status: 204):**

## List commit comments

```
GET /repos/{owner}/{repo}/commits/{commit_sha}/comments
```

Lists the comments for a specified commit.
This endpoint supports the following custom media types. For more information, see "Media types."

application/vnd.github-commitcomment.raw+json: Returns the raw markdown body. Response will include body. This is the default if you do not pass any specific media type.
application/vnd.github-commitcomment.text+json: Returns a text only representation of the markdown body. Response will include body\_text.
application/vnd.github-commitcomment.html+json: Returns HTML rendered from the body's markdown. Response will include body\_html.
application/vnd.github-commitcomment.full+json: Returns raw, text, and HTML representations. Response will include body, body\_text, and body\_html.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`commit_sha`** (string) (required)
  The SHA of the commit.

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
  https://api.github.com/repos/OWNER/REPO/commits/COMMIT_SHA/comments
```

**Response schema (Status: 200):**

Same response schema as [List commit comments for a repository](#list-commit-comments-for-a-repository).

## Create a commit comment

```
POST /repos/{owner}/{repo}/commits/{commit_sha}/comments
```

Create a comment for a commit using its :commit\_sha.
Access to commit comments can be controlled by organization owners. For more information, see "Managing commit comments for your organization".
This endpoint triggers notifications. Creating content too quickly using this endpoint may result in secondary rate limiting. For more information, see "Rate limits for the API" and "Best practices for using the REST API."
This endpoint supports the following custom media types. For more information, see "Media types."

application/vnd.github-commitcomment.raw+json: Returns the raw markdown body. Response will include body. This is the default if you do not pass any specific media type.
application/vnd.github-commitcomment.text+json: Returns a text only representation of the markdown body. Response will include body\_text.
application/vnd.github-commitcomment.html+json: Returns HTML rendered from the body's markdown. Response will include body\_html.
application/vnd.github-commitcomment.full+json: Returns raw, text, and HTML representations. Response will include body, body\_text, and body\_html.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`owner`** (string) (required)
  The account owner of the repository. The name is not case sensitive.

* **`repo`** (string) (required)
  The name of the repository without the .git extension. The name is not case sensitive.

* **`commit_sha`** (string) (required)
  The SHA of the commit.

#### Body parameters

* **`body`** (string) (required)
  The contents of the comment.

* **`path`** (string)
  Relative path of the file to comment on.

* **`position`** (integer)
  Line index in the diff to comment on.

* **`line`** (integer)
  Closing down notice. Use position parameter instead. Line number in the file to comment on.

### HTTP response status codes

* **201** - Created

* **403** - Forbidden

* **422** - Validation failed, or the endpoint has been spammed.

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X POST \
  https://api.github.com/repos/OWNER/REPO/commits/COMMIT_SHA/comments \
  -d '{
  "body": "Great stuff",
  "path": "file1.txt",
  "position": 4,
  "line": 1
}'
```

**Response schema (Status: 201):**

Same response schema as [Get a commit comment](#get-a-commit-comment).