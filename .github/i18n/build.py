#!/usr/bin/env python3
"""Build the English (en/) and German (de/) versions of the guide.

The French pages at the repository root are the source of truth. Their markup
is copied as is (same sections, ids and links); every visible text and every
translatable attribute is replaced by its entry in translations.json, keyed by
the French text. Asset paths get a "../" prefix so they still resolve from the
sub-folders.

The script also keeps two blocks in sync on every page, French included: the
FR / EN / DE language switch in the navigation and the hreflang links in the
head. A new French page therefore only needs its strings translated.

Usage (from anywhere, Python 3.8+ standard library only):

    python3 .github/i18n/build.py            # update the blocks, write en/ and de/
    python3 .github/i18n/build.py --missing  # list French strings without translation

Then run .github/i18n/check.py.
"""

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = Path(__file__).with_name('translations.json')
SITE_URL = 'https://guide.dodo-a-cassis.com/'

# Language code -> value of <html lang>. French stays at the site root.
LANGUAGES = {'fr': 'fr', 'en': 'en-GB', 'de': 'de'}
TARGETS = ('en', 'de')
LANGUAGE_NAMES = {'fr': 'Français', 'en': 'English', 'de': 'Deutsch'}
SWITCH_LABELS = {'fr': 'Langue', 'en': 'Language', 'de': 'Sprache'}

TRANSLATABLE_ATTRIBUTES = ('alt', 'title', 'aria-label')

TOKEN_RE = re.compile(r'<!--.*?-->|<(script|style)\b.*?</\1\s*>|<[!/]?[A-Za-z][^>]*>|[^<]+|<', re.S | re.I)
TAG_NAME_RE = re.compile(r'<\s*(/?)([A-Za-z][A-Za-z0-9]*)')
ATTRIBUTE_RE = re.compile(r'(\s(%s)=")([^"]*)(")' % '|'.join(TRANSLATABLE_ATTRIBUTES))
CONTENT_RE = re.compile(r'(\s(content)=")([^"]*)(")')
URL_ATTRIBUTE_RE = re.compile(r'(\s(?:src|href)=")([^"]*)(")')
STYLE_URL_RE = re.compile(r'''url\((['"]?)([^'")]+)\1\)''')
SCHEME_RE = re.compile(r'^(?:[A-Za-z][A-Za-z0-9+.-]*:|//|#)')

SWITCH_RE = re.compile(r'\n[ \t]*<div class="lang-switch".*?</div>', re.S)
NAV_LINKS_END_RE = re.compile(r'(<ul class="nav__links"[^>]*>.*?</ul>)', re.S)
HREFLANG_RE = re.compile(r'(?:\n[ \t]*<link rel="alternate" hreflang="[^"]*" href="[^"]*">)+')
TITLE_RE = re.compile(r'\n([ \t]*)<title>.*?</title>', re.S)
DESCRIPTION_RE = re.compile(r'<meta\s[^>]*name="description"')

SWITCH_PLACEHOLDER = '<!--i18n:lang-switch-->'
HREFLANG_PLACEHOLDER = '<!--i18n:hreflang-->'


def french_pages():
    return sorted(path.name for path in ROOT.glob('*.html'))


def normalise(text):
    return ' '.join(html.unescape(text).split())


def has_letters(text):
    return any(char.isalpha() for char in text)


def escape_attribute(text):
    return html.escape(text, quote=False).replace('"', '&quot;')


def page_url(lang, page):
    folder = '' if lang == 'fr' else lang + '/'
    return SITE_URL + folder + ('' if page == 'index.html' else page)


def relative_href(from_lang, to_lang, page):
    up = '' if from_lang == 'fr' else '../'
    folder = '' if to_lang == 'fr' else to_lang + '/'
    return up + folder + page


def hreflang_block(page, indent):
    links = [(lang, page_url(lang, page)) for lang in LANGUAGES]
    links.append(('x-default', page_url('fr', page)))
    return ''.join('\n%s<link rel="alternate" hreflang="%s" href="%s">' % (indent, code, url) for code, url in links)


def switch_block(lang, page, indent):
    lines = ['\n%s<div class="lang-switch" role="group" aria-label="%s">' % (indent, SWITCH_LABELS[lang])]
    for code in LANGUAGES:
        attributes = 'lang="%s" title="%s"' % (code, LANGUAGE_NAMES[code])
        if code == lang:
            item = '<span class="lang-switch__item lang-switch__item--current" %s aria-current="true">%s</span>' % (attributes, code.upper())
        else:
            item = '<a href="%s" class="lang-switch__item" hreflang="%s" %s>%s</a>' % (relative_href(lang, code, page), code, attributes, code.upper())
        lines.append('\n%s    %s' % (indent, item))
    lines.append('\n%s</div>' % indent)
    return ''.join(lines)


def line_indent(source, position):
    start = source.rfind('\n', 0, position) + 1
    return re.match(r'[ \t]*', source[start:]).group(0)


def with_placeholders(source, page):
    """Swap the language switch and hreflang blocks for placeholders, adding them if missing."""
    source = SWITCH_RE.sub('', source)
    source = HREFLANG_RE.sub('', source)
    nav_links = NAV_LINKS_END_RE.search(source)
    title = TITLE_RE.search(source)
    if not nav_links or not title:
        raise SystemExit('%s: no <ul class="nav__links"> or <title> found' % page)
    source = source[:nav_links.end()] + SWITCH_PLACEHOLDER + source[nav_links.end():]
    title = TITLE_RE.search(source)
    return source[:title.end()] + HREFLANG_PLACEHOLDER + source[title.end():]


def fill_placeholders(source, lang, page):
    switch_at = source.index(SWITCH_PLACEHOLDER)
    source = source.replace(SWITCH_PLACEHOLDER, switch_block(lang, page, line_indent(source, switch_at)))
    hreflang_at = source.index(HREFLANG_PLACEHOLDER)
    return source.replace(HREFLANG_PLACEHOLDER, hreflang_block(page, line_indent(source, hreflang_at)))


def tokenise(source):
    tokens = [match.group(0) for match in TOKEN_RE.finditer(source)]
    if ''.join(tokens) != source:
        raise SystemExit('tokeniser lost characters')
    return tokens


def localise_url(url, tag):
    """Prefix local asset URLs with ../ ; links between guide pages stay in the same language."""
    if not url or SCHEME_RE.match(url):
        return url
    if tag == 'a' and url.split('#')[0].endswith('.html'):
        return url
    return '../' + url


class Translator:
    def __init__(self, catalogue, lang):
        self.catalogue = catalogue
        self.lang = lang
        self.missing = []
        self.used = set()

    def text(self, french):
        key = normalise(french)
        entry = self.catalogue.get(key)
        if entry is None or not entry.get(self.lang):
            self.missing.append(key)
            return key
        self.used.add(key)
        return entry[self.lang]

    def tag(self, token, name):
        def attribute(match):
            if not has_letters(match.group(3)):
                return match.group(0)
            return match.group(1) + escape_attribute(self.text(match.group(3))) + match.group(4)

        token = ATTRIBUTE_RE.sub(attribute, token)
        if name == 'meta' and 'name="description"' in token:
            token = CONTENT_RE.sub(attribute, token)
        if name == 'html':
            token = token.replace('lang="fr"', 'lang="%s"' % LANGUAGES[self.lang])
        token = URL_ATTRIBUTE_RE.sub(lambda m: m.group(1) + localise_url(m.group(2), name) + m.group(3), token)
        return STYLE_URL_RE.sub(lambda m: 'url(%s%s%s)' % (m.group(1), localise_url(m.group(2), 'img'), m.group(1)), token)

    def page(self, source):
        """Translate a French page (placeholders already in place). Returns (html, hero subtitle)."""
        output = []
        subtitle_next = False
        subtitle = None
        for token in tokenise(source):
            if token.startswith('<!--') or token.lower().startswith(('<script', '<style', '<!doctype')):
                output.append(token)
                continue
            tag = TAG_NAME_RE.match(token) if token.startswith('<') else None
            if tag:
                closing, name = tag.group(1), tag.group(2).lower()
                subtitle_next = not closing and 'class="hero__subtitle"' in token
                output.append(self.tag(token, name))
                continue
            if token.isspace() or not has_letters(html.unescape(token)):
                output.append(token)
                continue
            leading = token[:len(token) - len(token.lstrip())]
            trailing = token[len(token.rstrip()):]
            translated = self.text(token)
            if subtitle_next and subtitle is None:
                subtitle = translated
            subtitle_next = False
            output.append(leading + html.escape(translated, quote=False) + trailing)
        return ''.join(output), subtitle


def add_description(source, description, page):
    if not description:
        raise SystemExit('%s: no hero subtitle to use as meta description' % page)
    title = TITLE_RE.search(source)
    meta = '\n%s<meta name="description" content="%s">' % (title.group(1), escape_attribute(description))
    return source[:title.end()] + meta + source[title.end():]


def add_notice(source, page):
    notice = ('<!-- Generated by .github/i18n/build.py from ../%s and .github/i18n/translations.json.'
              ' Edit those, then run the script again. -->\n' % page)
    return source.replace('<html', notice + '<html', 1)


def load_catalogue():
    with CATALOGUE.open(encoding='utf-8') as handle:
        return json.load(handle)


def build():
    """Return {relative path: content} for every page in the three languages, plus missing/unused strings."""
    catalogue = load_catalogue()
    outputs = {}
    missing = {}
    used = set()
    for page in french_pages():
        french = (ROOT / page).read_text(encoding='utf-8')
        template = with_placeholders(french, page)
        outputs[page] = fill_placeholders(template, 'fr', page)
        for lang in TARGETS:
            translator = Translator(catalogue, lang)
            translated, subtitle = translator.page(template)
            if not DESCRIPTION_RE.search(translated):
                # The French pages have no meta description: use the translated hero subtitle.
                translated = add_description(translated, subtitle, page)
            outputs['%s/%s' % (lang, page)] = add_notice(fill_placeholders(translated, lang, page), page)
            for key in translator.missing:
                missing.setdefault(key, set()).add(lang)
            used |= translator.used
    unused = [key for key in catalogue if key not in used]
    return outputs, missing, unused


def main():
    outputs, missing, unused = build()
    if missing:
        skeleton = {key: {lang: '' for lang in TARGETS} for key in missing}
        print(json.dumps(skeleton, ensure_ascii=False, indent=2))
        print('\n%d French string(s) without translation, nothing written.' % len(missing), file=sys.stderr)
        return 1
    if '--missing' in sys.argv:
        print('All French strings are translated.')
        return 0
    for key in unused:
        print('warning: unused entry in translations.json: %r' % key, file=sys.stderr)
    changed = 0
    for relative, content in outputs.items():
        path = ROOT / relative
        if path.exists() and path.read_text(encoding='utf-8') == content:
            continue
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, encoding='utf-8')
        changed += 1
        print('wrote %s' % relative)
    print('%d page(s) up to date, %d written.' % (len(outputs) - changed, changed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
