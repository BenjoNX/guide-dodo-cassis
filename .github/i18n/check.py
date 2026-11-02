#!/usr/bin/env python3
"""Check the French, English and German versions of the guide.

    python3 .github/i18n/check.py

Exits with status 1 if a check fails:

  1. en/ and de/ are exactly what build.py generates (no hand edits, no missing string);
  2. every page is well formed: balanced tags, unique ids;
  3. every local link, image and stylesheet exists, and every #anchor exists in its page;
  4. <html lang>, title, meta description and hreflang links of every page;
  5. FR, EN and DE pages share the same skeleton (tags, ids, classes, links, images);
  6. no French left in EN / DE: a string identical to the French one must carry a "keep"
     justification in translations.json, every other string is scanned for French words;
  7. German addresses the reader with "Sie" only, English uses British spelling.

Standard library only. Warnings (known issues inherited from the French pages) do not fail.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ next to the scripts
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

ROOT = build.ROOT
VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}

# Anchors the French guide links to without defining them. Mirrored as is in EN / DE so the
# three versions keep the same anchors; fixing them belongs to the French content.
KNOWN_MISSING_ANCHORS = {
    'visiter-environs.html#plus-loin': 'the "Plus loin..." card of the home page targets an id '
                                       'that visiter-environs.html does not define (French page)',
}

# Proper nouns and loanwords allowed inside translated sentences (French spelling kept on purpose).
PROPER_NOUNS = [
    "L'Arrivée d'un train en gare de La Ciotat", 'Dodo à Cassis', 'La Conciergerie Cassidaine',
    "Calanque d'En-Vau", 'Calanque de Figuerolles', 'Calanque du Mugel', 'Calanque de Sormiou',
    'Route des Crêtes', 'Cap Canaille', 'Port-Pin', 'En-Vau', "Bec de l'Aigle", 'Rocher du Capucin',
    "Notre-Dame-de-l'Assomption", 'Notre-Dame de la Garde', 'Bonne Mère', 'Vieille Charité',
    'Jardin des Migrations', 'Fort Saint-Jean', 'Les Deux Garçons', 'Cours Mirabeau', 'Saint-Sauveur',
    'Sainte-Victoire', "Caumont Centre d'Art", 'Atelier Cézanne', 'Place Richelme', 'Place des Prêcheurs',
    'Lac de Sainte-Croix', "Pont d'Avignon", "Festival d'Avignon", 'Palais des Papes', 'Gorges du Verdon',
    "Îles d'Hyères", 'Île Verte', 'Vendanges Étoilées', 'Voiles de Cassis', 'Grotte Cosquer',
    'Cosquer Méditerranée', 'Mes Calanques', 'MesCalanques', 'La Marcouline', "La Cadière d'Azur",
    'Le Castellet', 'Le Lavandou', 'Le Mugel', 'Le Panier', 'Bormes-les-Mimosas', 'Sanary-sur-Mer',
    'Aix-en-Provence', 'La Ciotat', 'Domaine du Bagnol', 'Clos Sainte-Magdeleine', 'Clos de Fontcreuse',
    'Vieux-Port', 'Cézanne', 'Lumière', 'Provençal', 'café', 'cafés', 'Cafés', 'rosé', 'rosés', 'Rosé',
    'Rosés', 'façades', 'Pointu', 'pointu', 'SIRET', 'RCS',
]
FRENCH_WORDS = {'le', 'la', 'les', 'des', 'du', 'de', 'et', 'à', 'au', 'aux', 'pour', 'avec', 'dans', 'sur',
                'vous', 'nous', 'nos', 'notre', 'votre', 'vos', 'une', 'un', 'est', 'sont', 'depuis', 'tous',
                'toutes', 'toute', 'très', 'ou', 'où', 'qui', 'que', 'cette', 'ces', 'chez', 'sans', 'entre',
                'vers', 'leur', 'leurs', 'il', 'elle', 'ils', 'elles', 'mais', 'donc', 'jours', 'gratuit'}
FRENCH_WORDS_ALSO_GERMAN = {'des'}
FRENCH_LETTERS = {'en': 'àâæçéèêëîïôœùûüÿ', 'de': 'àâæçéèêëîïôœùûÿ'}
FRENCH_ELISION_RE = re.compile(r"\b[cdjlmnst]'\w", re.I)
GERMAN_INFORMAL_RE = re.compile(r'\b(du|dich|dir|dein\w*|euch|euer|eure\w*)\b', re.I)
US_SPELLING_RE = re.compile(r'\b(color\w*|favor\w*|center\w*|theater\w*|meters?|kilometers?|traveler\w*|traveling|'
                            r'neighbor\w*|harbor\w*|organiz\w*|realiz\w*|gray|vacation\w*|cozy)\b', re.I)


class Page(HTMLParser):
    """Collects what the checks need from one HTML file."""

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.errors = []
        self.stack = []
        self.ids = []
        self.urls = []            # (tag, attribute, url)
        self.skeleton = []        # start tags of <body>, without the language switch
        self.units = []           # (kind, text) translatable texts in document order
        self.lang = None
        self.description = None
        self.hreflang = []
        self.in_body = False
        self.switch_depth = None
        self.feed(path.read_text(encoding='utf-8'))
        self.close()
        for tag, line in self.stack:
            self.errors.append('<%s> opened line %d is never closed' % (tag, line))

    def in_switch(self):
        return self.switch_depth is not None

    def handle_starttag(self, tag, attrs, self_closing=False):
        attributes = dict(attrs)
        line = self.getpos()[0]
        if tag == 'html':
            self.lang = attributes.get('lang')
        if tag == 'body':
            self.in_body = True
        if 'id' in attributes:
            self.ids.append(attributes['id'])
        if tag == 'div' and attributes.get('class') == 'lang-switch':
            self.switch_depth = len(self.stack)
        if tag == 'meta' and attributes.get('name') == 'description':
            self.description = attributes.get('content', '')
        if tag == 'link' and attributes.get('rel') == 'alternate' and 'hreflang' in attributes:
            self.hreflang.append((attributes['hreflang'], attributes.get('href', '')))
        for name in ('href', 'src'):
            if name in attributes and not (tag == 'link' and attributes.get('rel') == 'alternate'):
                self.urls.append((tag, name, attributes[name]))
        for url in build.STYLE_URL_RE.findall(attributes.get('style', '')):
            self.urls.append((tag, 'style', url[1]))
        if not self.in_switch():
            for name in build.TRANSLATABLE_ATTRIBUTES:
                if build.has_letters(attributes.get(name, '')):
                    self.units.append(('%s@%s' % (name, tag), attributes[name]))
            if self.in_body:
                self.skeleton.append((tag, attributes.get('id'), attributes.get('class'),
                                      strip_up(attributes.get('href')), strip_up(attributes.get('src')),
                                      build.STYLE_URL_RE.sub(lambda m: 'url(%s)' % strip_up(m.group(2)),
                                                             attributes.get('style', ''))))
        if tag not in VOID_ELEMENTS and not self_closing:
            self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs, self_closing=True)

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            return
        if not self.stack or self.stack[-1][0] != tag:
            expected = self.stack[-1][0] if self.stack else 'nothing'
            self.errors.append('line %d: </%s> closes <%s>' % (self.getpos()[0], tag, expected))
            if any(open_tag == tag for open_tag, _ in self.stack):
                while self.stack and self.stack.pop()[0] != tag:
                    pass
            return
        self.stack.pop()
        if self.switch_depth is not None and len(self.stack) == self.switch_depth:
            self.switch_depth = None

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] in ('script', 'style'):
            return
        if build.has_letters(data) and not self.in_switch():
            self.units.append(('text', data))


def strip_up(url):
    return url[3:] if url and url.startswith('../') else url


def pages():
    names = build.french_pages()
    return {lang: {name: ROOT / ('' if lang == 'fr' else lang) / name for name in names} for lang in build.LANGUAGES}


def strip_proper_nouns(text, extra):
    for noun in sorted(set(PROPER_NOUNS) | extra, key=len, reverse=True):
        text = text.replace(noun, ' ')
    return text


def french_markers(text, lang, extra):
    """Words or letters that look French once proper nouns are removed."""
    text = strip_proper_nouns(text, extra)
    words = re.findall(r"[^\W\d_]+", text)
    french = FRENCH_WORDS - (FRENCH_WORDS_ALSO_GERMAN if lang == 'de' else set())
    found = [word for word in words if word.lower() in french]
    found += [word for word in words if any(char in FRENCH_LETTERS[lang] for char in word.lower())]
    found += FRENCH_ELISION_RE.findall(text)
    return sorted(set(found))


def main():
    errors, warnings, kept = [], [], {}
    catalogue = build.load_catalogue()
    # Names kept identical (places, brands) may also appear inside translated sentences.
    keep_nouns = {key for key, entry in catalogue.items() if entry.get('keep') and len(key) > 3}

    # 1. Generated pages are up to date.
    outputs, missing, _ = build.build()
    for key in missing:
        errors.append('translations.json: no translation for %r' % key)
    for relative, content in outputs.items():
        path = ROOT / relative
        if not path.exists() or path.read_text(encoding='utf-8') != content:
            errors.append('%s is not up to date: run .github/i18n/build.py' % relative)

    parsed = {lang: {name: Page(path) for name, path in files.items() if path.exists()}
              for lang, files in pages().items()}

    for lang, files in parsed.items():
        for name, page in files.items():
            where = page.path.relative_to(ROOT)
            # 2. Well formed.
            errors += ['%s: %s' % (where, error) for error in page.errors]
            duplicates = sorted({i for i in page.ids if page.ids.count(i) > 1})
            if duplicates:
                errors.append('%s: duplicate ids %s' % (where, duplicates))
            # 3. Local links, images, stylesheets and anchors.
            for tag, attribute, url in page.urls:
                if build.SCHEME_RE.match(url) and not url.startswith('#'):
                    continue
                target_part, _, anchor = url.partition('#')
                target = (page.path.parent / target_part).resolve() if target_part else page.path
                if not target.exists():
                    errors.append('%s: <%s %s="%s"> points to a missing file' % (where, tag, attribute, url))
                    continue
                if anchor and target.suffix == '.html':
                    target_page = parsed_page(parsed, target) or Page(target)
                    if anchor not in target_page.ids:
                        known = KNOWN_MISSING_ANCHORS.get('%s#%s' % (target.name, anchor))
                        message = '%s: link to %s has no target id "%s"' % (where, url, anchor)
                        if known:
                            warnings.append('%s (known, %s)' % (message, known))
                        else:
                            errors.append(message)
            # 4. Language, title, description, hreflang.
            if page.lang != build.LANGUAGES[lang]:
                errors.append('%s: <html lang="%s">, expected "%s"' % (where, page.lang, build.LANGUAGES[lang]))
            if not any(kind == 'text' for kind, _ in page.units):
                errors.append('%s: no text found' % where)
            if lang != 'fr' and not page.description:
                errors.append('%s: no meta description' % where)
            expected = [(code, build.page_url(code, name)) for code in build.LANGUAGES]
            expected.append(('x-default', build.page_url('fr', name)))
            if page.hreflang != expected:
                errors.append('%s: hreflang links %s, expected %s' % (where, page.hreflang, expected))
            for _, url in page.hreflang:
                local = ROOT / url[len(build.SITE_URL):]
                if not (local / 'index.html' if url.endswith('/') else local).exists():
                    errors.append('%s: hreflang URL %s has no file' % (where, url))

    for lang in build.TARGETS:
        for name, page in parsed[lang].items():
            french = parsed['fr'].get(name)
            where = page.path.relative_to(ROOT)
            if french is None:
                errors.append('%s has no French counterpart' % where)
                continue
            # 5. Same skeleton as the French page.
            if page.skeleton != french.skeleton:
                for index, (ours, theirs) in enumerate(zip(page.skeleton, french.skeleton)):
                    if ours != theirs:
                        errors.append('%s: markup differs from the French page at tag #%d: %s vs %s'
                                      % (where, index, ours, theirs))
                        break
                else:
                    errors.append('%s: %d tags, the French page has %d' % (where, len(page.skeleton), len(french.skeleton)))
            if len(page.units) != len(french.units):
                errors.append('%s: %d texts, the French page has %d' % (where, len(page.units), len(french.units)))
                continue
            # 6. French left in EN / DE.
            if page.description and build.normalise(page.description) in catalogue:
                errors.append('%s: meta description is still in French' % where)
            for (kind, text), (_, french_text) in zip(page.units, french.units):
                ours, theirs = build.normalise(text), build.normalise(french_text)
                if ours == theirs:
                    entry = catalogue.get(theirs, {})
                    note = entry.get('keep') if entry.get(lang) == theirs else None
                    if note:
                        kept.setdefault((ours, note), set()).add(lang)
                    else:
                        errors.append('%s: %s %r is identical to the French text without justification' % (where, kind, ours))
                    continue
                markers = french_markers(ours, lang, keep_nouns)
                if markers:
                    errors.append('%s: %s %r looks French (%s)' % (where, kind, ours, ', '.join(markers)))
                # 7. Register and spelling.
                plain = strip_proper_nouns(ours, keep_nouns)
                if lang == 'de' and GERMAN_INFORMAL_RE.search(plain):
                    errors.append('%s: informal German in %r' % (where, ours))
                if lang == 'en' and US_SPELLING_RE.search(plain):
                    errors.append('%s: US spelling %r in %r' % (where, US_SPELLING_RE.search(plain).group(0), ours))
            if page.description:
                plain = strip_proper_nouns(page.description, keep_nouns)
                if french_markers(page.description, lang, keep_nouns) or (lang == 'de' and GERMAN_INFORMAL_RE.search(plain)):
                    errors.append('%s: meta description looks wrong: %r' % (where, page.description))

    report(parsed, kept, warnings, errors)
    return 1 if errors else 0


def parsed_page(parsed, path):
    for files in parsed.values():
        for page in files.values():
            if page.path.resolve() == path:
                return page
    return None


def report(parsed, kept, warnings, errors):
    count = sum(len(files) for files in parsed.values())
    print('Checked %d pages (%s).' % (count, ', '.join('%s: %d' % (lang, len(files)) for lang, files in parsed.items())))
    if kept:
        print('\nStrings kept identical to the French text in EN / DE (justification from translations.json):')
        for (text, note), langs in sorted(kept.items(), key=lambda item: (item[0][1], item[0][0])):
            print('  [%s] %s  (%s)' % ('/'.join(sorted(langs)).upper(), text, note))
    for warning in warnings:
        print('\nwarning: %s' % warning)
    if errors:
        print('\n%d error(s):' % len(errors))
        for error in errors:
            print('  - %s' % error)
    else:
        print('\nAll checks passed.')


if __name__ == '__main__':
    sys.exit(main())
