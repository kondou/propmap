#!/usr/bin/env python3
"""
PropMap_UserGuide_ja.html / PropMap_UserGuide_en.html を生成するスクリプト
使い方: cd ~/heatmap && python3 generate_guides.py
"""
import base64, re, markdown
from pathlib import Path

def _embed_images(html, base_dir):
    def replace(m):
        img_path = base_dir / m.group(1)
        if not img_path.exists():
            return m.group(0)
        ext = img_path.suffix.lower().lstrip('.')
        mime = 'image/png' if ext == 'png' else f'image/{ext}'
        data = base64.b64encode(img_path.read_bytes()).decode('ascii')
        return f'src="data:{mime};base64,{data}"'
    return re.sub(r'src="(images/[^"]+)"', replace, html)

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  font-size: 15px;
  line-height: 1.75;
  color: #d4d4d4;
  background: #1a1a1a;
  max-width: 100%;
  margin: 0;
  padding: 32px 48px 80px;
}
h1 { font-size: 1.9em; border-bottom: 2px solid #444; padding-bottom: 0.35em; margin: 0.6em 0 0.8em; color: #e8e8e8; }
h2 { font-size: 1.4em; border-bottom: 1px solid #333; padding-bottom: 0.25em; margin: 2.2em 0 0.8em; color: #e0e0e0; }
h3 { font-size: 1.1em; margin: 1.6em 0 0.5em; color: #d8d8d8; }
h4 { font-size: 1em; margin: 1.2em 0 0.4em; color: #cccccc; }
p { margin: 0.7em 0; }
ul, ol { padding-left: 1.6em; margin: 0.6em 0; }
li { margin: 0.3em 0; }
a { color: #7ab3e0; text-decoration: none; }
a:hover { text-decoration: underline; }
strong { font-weight: 600; color: #e8e8e8; }
code {
  font-family: 'SF Mono', 'Fira Code', Consolas, 'Courier New', monospace;
  font-size: 0.875em;
  background: #2a2a2a;
  padding: 2px 6px;
  border-radius: 4px;
  color: #e06c75;
}
pre {
  background: #242424;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  padding: 16px;
  overflow-x: auto;
  margin: 1em 0;
  position: relative;
  width: fit-content;
  min-width: 20em;
}
pre code {
  background: none;
  padding: 0;
  color: #d4d4d4;
  font-size: 0.875em;
  line-height: 1.5;
}
.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 3px 10px;
  font-size: 11px;
  background: #2a2a2a;
  border: 1px solid #555;
  border-radius: 4px;
  cursor: pointer;
  color: #aaa;
  opacity: 0;
  transition: opacity 0.15s;
}
pre:hover .copy-btn { opacity: 1; }
.copy-btn:hover { background: #333; }
.copy-btn.copied { background: #28a745; color: #fff; border-color: #28a745; opacity: 1; }
table {
  border-collapse: collapse;
  width: auto;
  max-width: 100%;
  margin: 1em 0;
  font-size: 0.92em;
}
th, td { border: 1px solid #3a3a3a; padding: 8px 14px; text-align: left; }
th { background: #2a2a2a; font-weight: 600; color: #e0e0e0; }
tr:nth-child(even) td { background: #222; }
blockquote {
  border-left: 4px solid #555;
  margin: 1em 0;
  padding: 0.6em 1.2em;
  color: #aaa;
  background: #242424;
  border-radius: 0 4px 4px 0;
}
blockquote p { margin: 0; }
hr { border: none; border-top: 1px solid #333; margin: 2em 0; }
img { max-width: 100%; height: auto; display: block; margin: 1em 0; border-radius: 4px; }
@media (max-width: 640px) {
  body { padding: 16px 18px 60px; }
  h1 { font-size: 1.5em; }
  h2 { font-size: 1.25em; }
}
"""

JS = """
document.querySelectorAll('pre').forEach(pre => {
  if (pre.querySelector('code.language-no-copy')) return;
  const btn = document.createElement('button');
  btn.className = 'copy-btn';
  btn.textContent = 'Copy';
  btn.addEventListener('click', () => {
    const code = pre.querySelector('code');
    const text = code ? code.textContent : pre.textContent;
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
    }).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
    });
  });
  pre.appendChild(btn);
});
"""

def convert(md_path, html_path, lang, title):
    base_dir = Path(md_path).parent
    md_text = Path(md_path).read_text(encoding='utf-8')
    md_engine = markdown.Markdown(
        extensions=['tables', 'fenced_code', 'toc', 'attr_list'],
        extension_configs={'toc': {'anchorlink': False}}
    )
    body = md_engine.convert(md_text)
    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
{body}
<script>{JS}</script>
</body>
</html>"""
    html = _embed_images(html, base_dir)
    Path(html_path).write_text(html, encoding='utf-8')
    print(f"Generated: {html_path}")

BASE = Path(__file__).parent

convert(
    BASE / 'PropMap_UserGuide.md',
    BASE / 'PropMap_UserGuide_ja.html',
    'ja',
    'PropMap ユーザーガイド'
)

en_md = BASE / 'PropMap_UserGuide_en.md'
if en_md.exists():
    convert(
        en_md,
        BASE / 'PropMap_UserGuide_en.html',
        'en',
        'PropMap User Guide'
    )
else:
    print(f"Skipped English (not found): {en_md}")
