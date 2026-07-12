# EveryGPT Image Gen

Codex skill for generating images and editing reference images through the EveryGPT OpenAI-compatible API.

The skill discovers the currently available models from `https://api.everygpt.site/v1/models`, requires the user to choose a model and aspect ratio when they are not specified, converts the aspect ratio to the correct pixel size, and saves generated images to the system temporary directory.

## Requirements

- Python 3.9 or newer. The bundled script uses only the Python standard library.
- An EveryGPT API key.
- Network access to `https://api.everygpt.site/v1`.

## Download And Install

Clone the repository:

```bash
git clone https://github.com/plxj6666/EveryGPT-Imagen.git
```

To install it as a Codex skill, copy the skill directory into Codex's skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R EveryGPT-Imagen/everygpt-image-gen "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Restart or reload Codex if it does not immediately discover the new skill. Invoke it in a task with `$everygpt-image-gen`.

## Configure The API Key

Create a local configuration from the included template:

```bash
cd everygpt-image-gen
cp references/local_config.example.json references/local_config.json
chmod 600 references/local_config.json
```

Open `references/local_config.json` in an editor and set `api_key` to your EveryGPT key. Leave `base_url` as `https://api.everygpt.site/v1` unless you intentionally use a compatible endpoint.

`references/local_config.json` is ignored by Git and is not included in this repository. Never commit, share, paste into prompts, or place an API key in screenshots. Avoid passing a key through `--api-key` on a shared terminal because shell history and process listings can expose it.

## Use With Codex

Ask Codex normally, or invoke the skill directly:

```text
Use $everygpt-image-gen to create a cinematic product photo of a silver wireless speaker.
```

The skill follows this workflow:

1. Read the local configuration. If no key is configured, ask for one and store it only in `references/local_config.json`.
2. Query `/models`. If the user did not specify a model, show image-capable models and ask them to choose.
3. If neither a pixel size nor an aspect ratio was provided, show the five supported aspect ratios and their exact pixel sizes for the selected model, then ask the user to choose.
4. Generate or edit the image, save it to a temporary directory, and render the saved image path in the response.

Expected image models are `gpt-image2-1k`, `gpt-image2-2k`, and `gpt-image2-4k`. The API remains the source of truth: the model list is fetched at generation time.

## Aspect Ratios And Pixel Sizes

When a user chooses an aspect ratio, the script sends the corresponding `size` value to the API.

| Model | 1:1 | 3:4 | 4:3 | 9:16 | 16:9 |
| --- | --- | --- | --- | --- | --- |
| `gpt-image2-1k` | 1024x1024 | 768x1024 | 1024x768 | 576x1024 | 1024x576 |
| `gpt-image2-2k` | 2048x2048 | 1536x2048 | 2048x1536 | 1152x2048 | 2048x1152 |
| `gpt-image2-4k` | 4096x4096 | 3072x4096 | 4096x3072 | 2160x3840 | 3840x2160 |

For example, `gpt-image2-4k` with `16:9` sends `3840x2160`. An explicit pixel size supplied by the user is sent unchanged.

## Command Line Use

The Python script prints absolute paths to the saved images. Its default output directory is the system temporary directory.

List the current supported image models after configuring the API key:

```bash
python3 everygpt-image-gen/scripts/generate_image.py --list-models
```

Show the available aspect ratios and exact pixel sizes for a model:

```bash
python3 everygpt-image-gen/scripts/generate_image.py --list-sizes gpt-image2-4k
```

Generate an image:

```bash
python3 everygpt-image-gen/scripts/generate_image.py \
  "A cinematic product photo of a silver wireless speaker" \
  --model gpt-image2-4k \
  --aspect-ratio 16:9
```

Generate with an explicit output directory:

```bash
python3 everygpt-image-gen/scripts/generate_image.py \
  "Editorial illustration of a futuristic city at dawn" \
  --model gpt-image2-2k \
  --aspect-ratio 3:4 \
  --output-dir ./generated-images
```

Edit a reference image:

```bash
python3 everygpt-image-gen/scripts/generate_image.py \
  "Keep the composition and change the product finish to pearl white" \
  --model gpt-image2-2k \
  --aspect-ratio 1:1 \
  --image ./reference.png
```

## API And Output Behavior

- Model discovery: `GET /models`
- Image generation: `POST /images/generations`
- Reference-image editing: `POST /images/edits`
- Authentication: `Authorization: Bearer <api key>`
- Supported image responses: `data[].b64_json`, `data[].url`, and `data[].image_url`

Generated URLs can expire, so the script downloads URL-based results immediately. Temporary output files may be removed by the operating system; pass `--output-dir` when results must be retained.

## Repository Layout

```text
everygpt-image-gen/
  SKILL.md                         Codex skill instructions
  agents/openai.yaml               Codex UI metadata
  assets/                          Skill icons
  scripts/generate_image.py        API client and image downloader
  scripts/generate-image.ps1       PowerShell launcher
  references/api.md                API and size mapping reference
  references/local_config.example.json
```
