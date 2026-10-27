"""Digit speech adapted from WiM Calls' sayable(), with explicit verification-number support."""
import re

WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine')
IDENTIFIER = re.compile(r'(?:account(?:\s+(?:number|id))?|last\s+four(?:\s+(?:digits|of\s+my\s+social))?|social(?:\s+security)?(?:\s+number)?|ssn|pin|zip(?:\s+code)?|verification\s+code|confirmation(?:\s+(?:code|number))?|phone(?:\s+number)?)\s*(?:is|are|:|#)?\s*$', re.I)
MONEY = re.compile(r'\$\s*\d[\d,]*(?:\.\d+)?')
NUMBER = re.compile(r'(\$\s*)?\b(\d(?:[\d\- ]*\d)?)(\s*(?:dollars?|cents?|percent|%|bucks|minutes?|seconds?|hours?|days?|weeks?|months?|years?|people|pounds?|ounces?|miles?|am|pm))?\b', re.I)
SPEECH_GUIDANCE = ('Read account numbers, verification codes, last-four digits, and phone numbers one digit at a time. '
                   'Preserve every leading zero and the given grouping. Read dates, money, and ordinary quantities naturally.')


def digits(value):
    groups = re.findall(r'\d+', str(value))
    if not groups:
        return str(value)
    if all(len(group) == 1 for group in groups):
        return ' '.join(WORDS[int(group)] for group in groups)
    return ', '.join(' '.join(WORDS[int(char)] for char in group) for group in groups)


def prepare(text):
    text = str(text)
    amounts = [m.span() for m in MONEY.finditer(text)]
    def replace(match):
        money, number, unit = match.groups()
        if money or unit or any(start <= match.start() < end for start, end in amounts):
            return match.group(0)
        plain = re.sub(r'\D', '', number)
        explicit = IDENTIFIER.search(text[max(0, match.start()-100):match.start()])
        if not explicit and (len(plain) <= 2 or (re.fullmatch(r'(?:19|20)\d\d', plain) and not re.search(r'[- ]', number))):
            return match.group(0)
        return digits(number)
    return NUMBER.sub(replace, text)


def pronunciation_guide(facts):
    guide, seen = [], set()
    for fact in facts:
        text = str(fact)
        for match in NUMBER.finditer(text):
            money, number, unit = match.groups()
            if money or unit or not IDENTIFIER.search(text[max(0, match.start()-100):match.start()]):
                continue
            if number in seen:
                continue
            seen.add(number)
            guide.append({'word': number, 'pronunciation': digits(number)})
    return guide


def prepare_for_local(text):
    """Give Piper explicit currency units while preserving identifier speech."""
    spoken = prepare(text)
    def amount(match):
        value = match.group(0).replace('$', '').replace(',', '').strip()
        whole, _, fraction = value.partition('.')
        dollars = int(whole)
        cents = int((fraction + '00')[:2])
        parts = []
        if dollars or not cents:
            parts.append(f'{dollars} ' + ('dollar' if dollars == 1 else 'dollars'))
        if cents:
            parts.append(f'{cents} ' + ('cent' if cents == 1 else 'cents'))
        return ' and '.join(parts)
    return MONEY.sub(amount, spoken)
