"""Small allowlist for stored, user-authored reading/community HTML."""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

class CleanHTML(HTMLParser):
    tags={'p','br','strong','b','em','i','u','s','blockquote','ul','ol','li','h1','h2','h3','h4','pre','code','a','hr'}
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag not in self.tags:return
        attr=''
        if tag=='a':
            href=dict(attrs).get('href','') or ''
            if (href.startswith('/') and not href.startswith('//')) or urlsplit(href).scheme in ('http','https'):
                attr=' href="'+escape(href,quote=True)+'" rel="nofollow noopener noreferrer"'
        self.parts.append('<'+tag+attr+'>')
    def handle_endtag(self,tag):
        if tag in self.tags and tag not in ('br','hr'):self.parts.append('</'+tag+'>')
    def handle_data(self,text):self.parts.append(escape(text))

def clean_html(text):
    parser=CleanHTML();parser.feed(text or '');parser.close()
    return ''.join(parser.parts)

def reading_html(text):
    if '<p' in text or '<h' in text:return clean_html(text)
    return ''.join('<p>'+escape(p)+'</p>' for p in text.splitlines() if p.strip())


def plain_text(text):
    class Text(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
        def handle_data(self,data):self.parts.append(data)
        def handle_endtag(self,tag):
            if tag in ('p','div','li','h1','h2','h3','blockquote'):self.parts.append('\n')
        def handle_starttag(self,tag,attrs):
            if tag=='br':self.parts.append('\n')
    parser=Text();parser.feed(text or '');parser.close();return ''.join(parser.parts)
