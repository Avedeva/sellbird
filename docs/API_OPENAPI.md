# Authenticated OpenAPI schema

The dashboard intentionally keeps interactive documentation pages disabled at `/docs` and `/redoc`. The API schema is available at:

```text
GET /api/openapi.json
```

It is protected by the same dashboard bearer-token authentication as the other API routes. The schema describes the `/api/*` operations, including the product-scoped `POST /api/sales/discover` request and task-status response. `/api/instance` is public by existing design and is not included in the protected schema requirements.

The token is supplied by the dashboard's normal authenticated client; do not paste it into a public document or share it externally. Automated API clients should obtain/use credentials through the local dashboard setup and keep requests on the trusted local origin.
