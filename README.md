# slidebake

`slidebake` turns slide-deck PDFs, including image-only PDFs exported from PowerPoint,
into page-by-page Markdown. It uses local OCR first, then can ask the OpenAI API to
clean OCR noise and translate each page.

## Install

`slidebake` should be installed with Python 3.12. One of its OCR dependencies
does not currently support newer Python versions.

```bash
pipx install slidebake
```

For local development:

```bash
git clone https://github.com/heyifan142857/slidebake.git
cd slidebake
uv venv --python 3.12
uv sync
uv run slidebake --help
```

## Usage

```bash
slidebake slides.pdf -o slides.md
slidebake slides.pdf -o slides_zh.md --target-lang zh-CN
slidebake slides.pdf -o slides_bilingual.md --target-lang zh-CN --bilingual
```

Translation requires:

```bash
export OPENAI_API_KEY="your_api_key_here"
```

You can also put OpenAI or OpenAI-compatible provider settings in
`~/.config/slidebake/config.toml`:

```toml
[openai]
api_key = "your_api_key_here"
model = "gpt-5.4-mini"
api = "responses"
```

For providers that expose an OpenAI-compatible Chat Completions endpoint:

```toml
[openai]
api_key = "provider_api_key"
base_url = "https://api.example.com/v1"
model = "provider-model"
api = "chat_completions"
```

Command-line options and `SLIDEBAKE_OPENAI_*` environment variables override the
config file. Use `--config path/to/config.toml` to load a different config file.

Useful options:

- `--pages 1-10,15` limits processing to specific pages.
- `--dpi 220` changes render resolution for OCR.
- `--model gpt-5.4-mini` changes the OpenAI model.
- `--openai-base-url https://api.example.com/v1` uses an OpenAI-compatible endpoint.
- `--openai-api chat_completions` uses the Chat Completions compatibility path.
- `--check-key` checks resolved OpenAI-compatible settings without processing a PDF.
- `--keep-temp` keeps rendered page images for debugging.
- `--overwrite` replaces an existing output file.
