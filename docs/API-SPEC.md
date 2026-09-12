# API Specification — STYLELAB

Base:
`/api/v1`

## POST /profile/style

Creates or updates a style profile.

Input:
```json
{
  "occasion": "college",
  "vibe": "minimal-street",
  "fit_preference": "relaxed",
  "color_preferences": ["black", "white"]
}
```

## POST /tryon/upload

Accepts an image upload.

Return:
```json
{
  "asset_id": "asset_123",
  "validation": {
    "valid": true,
    "warnings": []
  }
}
```

## POST /outfits/generate

```json
{
  "profile_id": "profile_123",
  "garment_ids": ["SKU1", "SKU2", "SKU3"],
  "occasion": "college",
  "vibe": "minimal-street"
}
```

Return:
```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

## GET /jobs/{job_id}

```json
{
  "job_id": "job_123",
  "status": "processing",
  "stage": "rendering",
  "progress": 0.7
}
```

## POST /outfits/{outfit_id}/remix

```json
{
  "slot": "bottom",
  "replacement_garment_id": "SKU998"
}
```

Return:
new job or updated outfit depending on implementation.

## POST /outfits/{outfit_id}/save

Idempotent save.

## DELETE /assets/{asset_id}

Deletes a user-owned image asset.

## Error contract

```json
{
  "error": {
    "code": "VTO_PROVIDER_TIMEOUT",
    "message": "We could not finish the visual generation.",
    "retryable": true,
    "request_id": "req_123"
  }
}
```

Never expose stack traces to users.
