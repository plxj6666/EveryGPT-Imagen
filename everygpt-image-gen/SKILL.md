---
name: everygpt-image-gen
description: Generate or edit images with the EveryGPT OpenAI-compatible API. Use when a user asks to create images, posters, product visuals, or reference-image variations through EveryGPT at https://api.everygpt.site/v1.
---

# EveryGPT Image Gen

Generate images from prompts or edit local reference images through the EveryGPT OpenAI-compatible API.

## Credential Check

Read `references/local_config.json` before any API call. On a fresh install, create it by copying `references/local_config.example.json`; it contains the base URL and the persisted `api_key`.

- If `api_key` is empty, ask the user to provide their EveryGPT API key. Do not call the API until they do.
- Persist the key in that same file, keeping `base_url` as `https://api.everygpt.site/v1`. Do not copy keys into logs, screenshots, generated artifacts, or the final response. Do not commit `local_config.json`.
- The Python script also persists a key passed with `--api-key`; do not put a supplied key on a shared terminal command line.
- For long-running image requests, an optional `origin_ip` in `references/local_config.json` (or `EVERYGPT_ORIGIN_IP`) makes the script connect directly to the API origin while retaining the HTTPS hostname for certificate validation. Use this only when the IP is the current EveryGPT origin; it bypasses Cloudflare's synchronous request timeout.

## Model And Size Selection

After a key is configured, query the current model list before image generation:

```bash
python3 /path/to/everygpt-image-gen/scripts/generate_image.py --list-models
```

If the user provides a model ID, use it. Otherwise, show the available image models and ask them to choose; do not silently select one. The expected image models are `gpt-image2-1k`, `gpt-image2-2k`, and `gpt-image2-4k`.

After the model is selected, check whether the user specified a size or aspect ratio. If neither was given, present these five aspect-ratio choices with the selected model's matching pixel dimensions and ask the user to choose one: `1:1`, `3:4`, `4:3`, `9:16`, `16:9`. Do not silently choose a ratio.

Use the script to display the exact candidates:

```bash
python3 /path/to/everygpt-image-gen/scripts/generate_image.py --list-sizes gpt-image2-4k
```

Pass the selected ratio as `--aspect-ratio`; the script sends the corresponding pixel `size`. For example, `gpt-image2-4k` with `16:9` sends `3840x2160`. If the user gives an explicit pixel size, pass it unchanged. For an unrecognized model without an explicit size, ask the user for one.

## Generate

Use the Python script because it has no third-party dependencies and saves images to the system temporary directory by default. It requests `response_format=url` by default and downloads the returned URL immediately, avoiding unnecessarily large Base64 responses:

```bash
python3 /path/to/everygpt-image-gen/scripts/generate_image.py "A cinematic product photo of a matte black smart speaker on a clean desk" --model gpt-image2-1k --aspect-ratio 1:1
```

Use repeated `--image` flags for reference-image edits:

```bash
python3 /path/to/everygpt-image-gen/scripts/generate_image.py "Keep the product shape, change the color to pearl white" --model gpt-image2-2k --aspect-ratio 3:4 --image ./reference.png
```

After generation, read the absolute paths printed by the script. Render each result in the response with Markdown image syntax and state that it was saved in the temporary directory.

If a request reports that the connection closed before JSON arrived, do not retry immediately: the upstream generation may already have completed and been billed. Check the EveryGPT log by request time first. A direct `origin_ip` avoids the usual cause for 4K requests.

## Prompting

Keep prompts specific and visual. Include subject, composition, style, lighting, background, and material constraints that affect the result. Create deliberate prompt variations when the user requests variants.

## API Details

Read `references/api.md` when debugging requests, response formats, or model-list behavior.
