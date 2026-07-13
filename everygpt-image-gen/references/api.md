# EveryGPT Image API Reference

Use `https://api.everygpt.site/v1` as the default base URL. The API is OpenAI-compatible for image operations.

## Authentication

Send `Authorization: Bearer <api key>`.

Copy `references/local_config.example.json` to `references/local_config.json`, then store the API key there. The bundled script can persist a key supplied with `--api-key`, but never print credentials. Do not commit `local_config.json`.

## Endpoints

- Text-to-image generation: `POST /images/generations`
- Image editing with uploaded file streams: `POST /images/edits`
- Model listing: `GET /models`

## Generation Body

```json
{
  "model": "gpt-image2-1k",
  "prompt": "A concise image prompt",
  "size": "3840x2160",
  "aspect_ratio": "16:9",
  "n": 1
}
```

When the user selects an aspect ratio, resolve the exact `size` from this table before sending the request:

| Model | 1:1 | 3:4 | 4:3 | 9:16 | 16:9 |
| --- | --- | --- | --- | --- | --- |
| `gpt-image2-1k` | 1024x1024 | 768x1024 | 1024x768 | 576x1024 | 1024x576 |
| `gpt-image2-2k` | 2048x2048 | 1536x2048 | 2048x1536 | 1152x2048 | 2048x1152 |
| `gpt-image2-4k` | 4096x4096 | 3072x4096 | 4096x3072 | 2160x3840 | 3840x2160 |

The bundled script defaults to `response_format: "url"` and downloads the returned image immediately. This keeps the API response small; it does not reduce the model's generation time.

Offer those five ratios when the user has not provided one. Pass a user-supplied explicit pixel size unchanged. Use an explicit size for other models.

## Edit Body

Use `multipart/form-data`.

Required fields:

- `model`
- `prompt`
- `image` file field; repeat `image` for multiple references when supported

Optional fields:

- `size`
- `quality`
- `n`

## Model Notes

Query `/models` at generation time. The expected EveryGPT image models are `gpt-image2-1k`, `gpt-image2-2k`, and `gpt-image2-4k`; do not rely on a stale static model list.

## Response Handling

Expect either:

```json
{"data": [{"b64_json": "..."}]}
```

or:

```json
{"data": [{"url": "https://..."}]}
```

Save `b64_json` as image bytes. Download `url` values promptly because provider URLs may expire.
