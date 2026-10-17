# REST API endpoints for GitHub App webhooks

Use the REST API to interact with webhooks for OAuth apps

## About webhooks for GitHub Apps

A GitHub App's webhook allows your server to receive HTTP `POST` payloads whenever certain events happen for a GitHub App. For more information, see [Webhooks documentation](/en/webhooks) and [Using webhooks with GitHub Apps](/en/apps/creating-github-apps/registering-a-github-app/using-webhooks-with-github-apps).

> \[!NOTE]
> Most endpoints use `Authorization: Bearer <YOUR-TOKEN>` and `Accept: application/vnd.github+json` headers, plus `X-GitHub-Api-Version: 2026-03-10`. Curl examples below omit these standard headers for brevity.

## Get a webhook configuration for an app

```
GET /app/hook/config
```

Returns the webhook configuration for a GitHub App. For more information about configuring a webhook for your app, see "Creating a GitHub App."
You must use a JWT to access this endpoint.

### HTTP response status codes

* **200** - OK

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/app/hook/config
```

**Response schema (Status: 200):**

* `url`: string, format: uri
* `content_type`: string
* `secret`: string
* `insecure_ssl`: one of:
  * **string**
  * **number**

## Update a webhook configuration for an app

```
PATCH /app/hook/config
```

Updates the webhook configuration for a GitHub App. For more information about configuring a webhook for your app, see "Creating a GitHub App."
You must use a JWT to access this endpoint.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Body parameters

* **`url`** (string)
  The URL to which the payloads will be delivered.

* **`content_type`** (string)
  The media type used to serialize the payloads. Supported values include json and form. The default is form.

* **`secret`** (string)
  If provided, the secret will be used as the key to generate the HMAC hex digest value for delivery signature headers.

* **`insecure_ssl`** (string or number)
  Determines whether the SSL certificate of the host for url will be verified when delivering payloads. Supported values include 0 (verification is performed) and 1 (verification is not performed). The default is 0. We strongly recommend not setting this to 1 as you are subject to man-in-the-middle and other attacks.

### HTTP response status codes

* **200** - OK

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X PATCH \
  https://api.github.com/app/hook/config \
  -d '{
  "content_type": "json",
  "insecure_ssl": "0",
  "secret": "********",
  "url": "https://example.com/webhook"
}'
```

**Response schema (Status: 200):**

Same response schema as [Get a webhook configuration for an app](#get-a-webhook-configuration-for-an-app).

## List deliveries for an app webhook

```
GET /app/hook/deliveries
```

Returns a list of webhook deliveries for the webhook configured for a GitHub App.
You must use a JWT to access this endpoint.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`per_page`** (integer)
  The number of results per page (max 100). For more information, see "Using pagination in the REST API."
  Default: `30`

* **`cursor`** (string)
  Used for pagination: the starting delivery from which the page of deliveries is fetched. Refer to the link header for the next and previous page cursors.

* **`status`** (string)
  Returns webhook deliveries filtered by delivery outcome classification based on status\_code range. A status of success returns deliveries with a status\_code in the 200-399 range (inclusive). A status of failure returns deliveries with a status\_code in the 400-599 range (inclusive).
  Can be one of: `success`, `failure`

### HTTP response status codes

* **200** - OK

* **400** - Bad Request

* **422** - Validation failed, or the endpoint has been spammed.

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/app/hook/deliveries
```

**Response schema (Status: 200):**

Array of `Simple webhook delivery`:

* `id`: required, integer, format: int64
* `guid`: required, string
* `delivered_at`: required, string, format: date-time
* `redelivery`: required, boolean
* `duration`: required, number
* `status`: required, string
* `status_code`: required, integer
* `event`: required, string
* `action`: required, string or null
* `installation_id`: required, integer or null, format: int64
* `repository_id`: required, integer or null, format: int64
* `throttled_at`: string or null, format: date-time

## Get a delivery for an app webhook

```
GET /app/hook/deliveries/{delivery_id}
```

Returns a delivery for the webhook configured for a GitHub App.
You must use a JWT to access this endpoint.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`delivery_id`** (integer) (required)

### HTTP response status codes

* **200** - OK

* **400** - Bad Request

* **422** - Validation failed, or the endpoint has been spammed.

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X GET \
  https://api.github.com/app/hook/deliveries/DELIVERY_ID
```

**Response schema (Status: 200):**

* `id`: required, integer
* `guid`: required, string
* `delivered_at`: required, string, format: date-time
* `redelivery`: required, boolean
* `duration`: required, number
* `status`: required, string
* `status_code`: required, integer
* `event`: required, string
* `action`: required, string or null
* `installation_id`: required, integer or null
* `repository_id`: required, integer or null
* `throttled_at`: string or null, format: date-time
* `url`: string
* `request`: required, object:
  * `headers`: required, object or null, additional properties allowed
  * `payload`: required, object or null, additional properties allowed
* `response`: required, object:
  * `headers`: required, object or null, additional properties allowed
  * `payload`: required, string or null, additional properties allowed

## Redeliver a delivery for an app webhook

```
POST /app/hook/deliveries/{delivery_id}/attempts
```

Redeliver a delivery for the webhook configured for a GitHub App.
You must use a JWT to access this endpoint.

### Parameters

#### Headers

* **`accept`** (string)
  Setting to `application/vnd.github+json` is recommended.

#### Path and query parameters

* **`delivery_id`** (integer) (required)

### HTTP response status codes

* **202** - Accepted

* **400** - Bad Request

* **422** - Validation failed, or the endpoint has been spammed.

### Code examples

#### Example

**Request:**

```curl
curl -L \
  -X POST \
  https://api.github.com/app/hook/deliveries/DELIVERY_ID/attempts
```

**Response schema (Status: 202):**

object