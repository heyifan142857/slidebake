# slidebake

`slidebake` turns slide-deck PDFs, including image-only PDFs exported from PowerPoint,
into page-by-page Markdown. It uses local OCR first, then can ask the OpenAI API to
clean OCR noise and translate each page.

## Install

```bash
pipx install .
```

For local development:

```bash
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

Useful options:

- `--pages 1-10,15` limits processing to specific pages.
- `--dpi 220` changes render resolution for OCR.
- `--model gpt-5.4-mini` changes the OpenAI model.
- `--keep-temp` keeps rendered page images for debugging.
- `--overwrite` replaces an existing output file.
