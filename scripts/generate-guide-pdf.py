#!/usr/bin/env python3
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak, CondPageBreak, Table, TableStyle, Preformatted
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/guia-didatico-banco-srjm.md'
OUTPUT = ROOT / 'docs/guia-didatico-banco-srjm.pdf'
FONT_ROOT = Path('/usr/share/fonts/truetype/dejavu')
for family, filename in [('Sans', 'DejaVuSans.ttf'), ('SansBold', 'DejaVuSans-Bold.ttf'), ('SansItalic', 'DejaVuSans-Oblique.ttf'), ('Mono', 'DejaVuSansMono.ttf')]:
    pdfmetrics.registerFont(TTFont(family, str(FONT_ROOT / filename)))
pdfmetrics.registerFontFamily('Sans', normal='Sans', bold='SansBold', italic='SansItalic', boldItalic='SansBold')
NAVY = colors.HexColor('#142C46')
TEAL = colors.HexColor('#087E8B')
TEXT = colors.HexColor('#25374B')
MUTED = colors.HexColor('#64748B')
LIGHT = colors.HexColor('#EFF5F8')
RULE = colors.HexColor('#D9E3EC')
WHITE = colors.white
PAGE_WIDTH, PAGE_HEIGHT = A4
WIDTH = PAGE_WIDTH - 88
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyGuide', fontName='Sans', fontSize=9.3, leading=13.6, textColor=TEXT, spaceAfter=8, splitLongWords=True))
styles.add(ParagraphStyle(name='ChapterGuide', fontName='SansBold', fontSize=18, leading=23, textColor=NAVY, spaceBefore=10, spaceAfter=16, keepWithNext=True))
styles.add(ParagraphStyle(name='CellGuide', fontName='Sans', fontSize=8.2, leading=11.3, textColor=TEXT, spaceAfter=0, splitLongWords=True))
styles.add(ParagraphStyle(name='HeadCellGuide', parent=styles['CellGuide'], fontName='SansBold', textColor=WHITE))
styles.add(ParagraphStyle(name='CodeGuide', fontName='Mono', fontSize=7.25, leading=10.1, textColor=TEXT, spaceAfter=0))
styles.add(ParagraphStyle(name='SmallGuide', parent=styles['BodyGuide'], fontSize=8.2, leading=12, textColor=MUTED))
styles.add(ParagraphStyle(name='BulletGuide', parent=styles['BodyGuide'], leftIndent=12, firstLineIndent=-10, spaceAfter=5))
styles.add(ParagraphStyle(name='CoverTitle', fontName='SansBold', fontSize=35, leading=42, textColor=NAVY, spaceAfter=18))
styles.add(ParagraphStyle(name='CoverSubtitle', fontName='Sans', fontSize=17, leading=25, textColor=TEAL, spaceAfter=18))


def inline(text):
    stash = []
    def hold(value):
        key = f'ZZINLINE{len(stash)}ZZ'
        stash.append((key, value))
        return key
    text = re.sub(r'`([^`]+)`', lambda m: hold('<font name="Mono" size="8">'+escape(m.group(1))+'</font>'), text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', lambda m: hold('<a href="'+escape(m.group(2), {'"':'&quot;'})+'" color="#087E8B">'+escape(m.group(1))+'</a>'), text)
    text = escape(text).replace('&lt;br/&gt;', '<br/>')
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    for key, value in stash:
        text = text.replace(key, value)
    return text


def para(text, style='BodyGuide'):
    return Paragraph(inline(text), styles[style])


def diagram(kind):
    if kind == 'REQUEST_FLOW':
        drawing = Drawing(WIDTH, 263)
        nodes = [('Navegador', 'Domínio público'), ('Cloudflare', 'DNS e proxy'), ('Classic ELB', 'Transporte TCP'), ('Istio Gateway', 'TLS e rotas'), ('Frontend', 'Knative + Nginx'), ('Rota interna', 'Gateway local'), ('Backend', 'Knative + Spring'), ('PostgreSQL', 'Disco EBS')]
        boxw, boxh, gap = 112, 58, (WIDTH-448)/3
        coords = [(i*(boxw+gap), 185) for i in range(4)] + [(i*(boxw+gap), 65) for i in reversed(range(4))]
        for i, ((title, subtitle), (x,y)) in enumerate(zip(nodes,coords)):
            drawing.add(Rect(x,y,boxw,boxh,rx=7,ry=7,fillColor=NAVY if i<4 else LIGHT,strokeColor=None))
            drawing.add(String(x+boxw/2,y+34,title,fontName='SansBold',fontSize=9.1,textAnchor='middle',fillColor=WHITE if i<4 else NAVY))
            drawing.add(String(x+boxw/2,y+17,subtitle,fontName='Sans',fontSize=7.8,textAnchor='middle',fillColor=WHITE if i<4 else TEXT))
        for i in range(7):
            x,y=coords[i]; nx,ny=coords[i+1]
            if i==3:
                arrow(drawing,x+boxw/2,y,nx+boxw/2,ny+boxh)
            elif i<3:
                arrow(drawing,x+boxw,y+boxh/2,nx,ny+boxh/2)
            else:
                arrow(drawing,x,y+boxh/2,nx+boxw,ny+boxh/2)
        drawing.add(String(0,28,'A chamada /api/ passa pelo frontend antes de alcançar o backend.',fontName='Sans',fontSize=8.2,fillColor=MUTED))
        drawing.add(String(0,13,'A resposta volta pelo caminho de entrada. Fluxo lógico simplificado.',fontName='Sans',fontSize=8.2,fillColor=MUTED))
    else:
        drawing=Drawing(WIDTH,125)
        if kind=='TLS_FLOW':
            labels=[('Navegador','TLS do visitante'),('Cloudflare','Nova conexão TLS'),('Classic ELB','Passagem TCP'),('Istio','Certificado da origem')]
            caption='Full (strict) valida o certificado da origem; o modo do painel não foi reconsultado.'
        else:
            labels=[('Vault','Origem dos dados'),('ESO + Store','Consulta por HTTPS'),('Secret','Objeto Kubernetes'),('Aplicação','Env ou volume')]
            caption='As credenciais não estão neste PDF. O app usa o Secret sincronizado.'
        boxw=112;gap=(WIDTH-448)/3
        for i,(title,subtitle) in enumerate(labels):
            x=i*(boxw+gap)
            drawing.add(Rect(x,48,boxw,60,rx=7,ry=7,fillColor=LIGHT,strokeColor=RULE))
            drawing.add(String(x+boxw/2,82,title,fontName='SansBold',fontSize=10,textAnchor='middle',fillColor=NAVY))
            drawing.add(String(x+boxw/2,64,subtitle,fontName='Sans',fontSize=7.4,textAnchor='middle',fillColor=TEXT))
            if i<3:arrow(drawing,x+boxw,78,x+boxw+gap,78)
        drawing.add(String(0,24,caption,fontName='Sans',fontSize=7.7,fillColor=MUTED))
    return drawing


def arrow(drawing,x1,y1,x2,y2):
    drawing.add(Line(x1,y1,x2,y2,strokeColor=TEAL,strokeWidth=1.4))
    if x1==x2:
        points=[x2,y2,x2-3,y2+6,x2+3,y2+6]
    elif x2>x1:
        points=[x2,y2,x2-5,y2-3,x2-5,y2+3]
    else:
        points=[x2,y2,x2+5,y2-3,x2+5,y2+3]
    drawing.add(Polygon(points,fillColor=TEAL,strokeColor=None))


class GuideDoc(BaseDocTemplate):
    def __init__(self):
        super().__init__(str(OUTPUT),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=62,bottomMargin=45,title='Banco SRJM — Guia didático de arquitetura e operação',author='Banco SRJM',subject='EKS, Classic ELB, Istio, Knative, Vault, Cloudflare, Helm e Argo CD')
        self.addPageTemplates(PageTemplate(id='Guide',frames=[Frame(44,45,WIDTH,PAGE_HEIGHT-107,id='main',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.decorate))
    def decorate(self,canvas,doc):
        canvas.saveState()
        if doc.page>1:
            canvas.setFillColor(TEAL)
            canvas.rect(44,PAGE_HEIGHT-30,27,3,fill=1,stroke=0)
            canvas.setFillColor(NAVY)
            canvas.setFont('SansBold',8)
            canvas.drawString(80,PAGE_HEIGHT-31,'BANCO SRJM  /  GUIA DE ESTUDO')
            canvas.setStrokeColor(RULE)
            canvas.line(44,32,PAGE_WIDTH-44,32)
            canvas.setFillColor(MUTED)
            canvas.setFont('Sans',7)
            canvas.drawString(44,20,'Base validada em 11/09/2026 • Comandos de referência')
            canvas.drawRightString(PAGE_WIDTH-44,20,str(doc.page))
        canvas.restoreState()
    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and getattr(flowable,'bookmark',None):
            text=flowable.getPlainText();key=flowable.bookmark
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text,key,0,False)
            self.notify('TOCEntry',(0,text,self.page,key))


def code_block(lines):
    text='\n'.join(lines)
    max_width=max((pdfmetrics.stringWidth(line,'Mono',7.25) for line in lines),default=0)
    if max_width>WIDTH-20:
        raise ValueError(f'Linha de comando larga demais ({max_width:.1f}): '+max(lines,key=len))
    code=Preformatted(text,styles['CodeGuide'])
    table=Table([[code]],colWidths=[WIDTH])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),0.5,RULE),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    return [table,Spacer(1,10)]


def markdown_table(lines):
    raw=[[cell.strip() for cell in line.strip().strip('|').split('|')] for line in lines]
    raw=[row for row in raw if not all(re.fullmatch(r'[:\- ]+',cell) for cell in row)]
    count=len(raw[0]);ratios=[.37,.63] if count==2 else [.26,.40,.34]
    table=Table([[para(cell,'HeadCellGuide' if i==0 else 'CellGuide') for cell in row] for i,row in enumerate(raw)],colWidths=[WIDTH*ratio for ratio in ratios],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE,LIGHT]),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),0.6,TEAL),('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]))
    return [table,Spacer(1,11)]


def main():
    story=[Spacer(1,36),para('GUIA DIDÁTICO • ARQUITETURA E OPERAÇÃO','SmallGuide'),Spacer(1,24),para('Banco SRJM','CoverTitle'),para('Da infraestrutura<br/>à aplicação','CoverTitle'),para('EKS · Istio · Knative · Vault<br/>Cloudflare · Helm · Argo CD','CoverSubtitle'),Spacer(1,20)]
    story.extend(markdown_table(['| Você vai aprender | Aplicação no projeto |','| --- | --- |','| Caminho da requisição | Do navegador ao PostgreSQL |','| Integração dos componentes | Quem cria e quem reconcilia cada recurso |','| Comandos de referência | Instalação, publicação e diagnóstico |','| Operação e recuperação | Revisões, Secrets, volumes e unseal |']))
    story.extend([Spacer(1,22),para('Edição de 12 de setembro de 2026','BodyGuide'),para('Baseado no ambiente validado em 11/09/2026. O material distingue recursos instalados de artefatos preparados para a migração. Nenhuma credencial foi incluída.','SmallGuide'),PageBreak()])
    lines=SOURCE.read_text().splitlines();i=0;chapter=0
    while i<len(lines):
        line=lines[i].strip()
        if not line or line.startswith('# ') or i<6:
            i+=1;continue
        if line=='[[TOC]]':
            story.append(para('Roteiro de leitura','ChapterGuide'))
            toc=TableOfContents();toc.levelStyles=[ParagraphStyle(name='TOCGuide',fontName='Sans',fontSize=10,leading=15,spaceBefore=11,textColor=TEXT,leftIndent=0,firstLineIndent=0)]
            story.extend([toc,Spacer(1,25),para('Os comandos são exemplos de referência para o ambiente descrito. Verifique contexto, dependências e ownership antes de reproduzir uma instalação.','SmallGuide')]);i+=1;continue
        if line.startswith('## '):
            chapter+=1
            story.append(PageBreak() if chapter in (1,13) else CondPageBreak(205))
            if chapter not in (1,13):
                story.append(Spacer(1,17))
            heading=para(line[3:],'ChapterGuide');heading.bookmark=f'chapter-{chapter}';story.append(heading);i+=1;continue
        if line.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].strip().startswith('```'):
                block.append(lines[i]);i+=1
            story.extend(code_block(block));i+=1;continue
        if line.startswith('|'):
            block=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                block.append(lines[i]);i+=1
            story.extend(markdown_table(block));continue
        if line.startswith('[['):
            story.extend([diagram(line[2:-2]),Spacer(1,4)]);i+=1;continue
        if line.startswith('- '):
            story.append(para('• '+line[2:],'BulletGuide'));i+=1;continue
        if re.match(r'^\d+\. ',line):
            story.append(para(line,'BodyGuide'));i+=1;continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].strip().startswith(('##','```','|','[[','- ')):
            paragraph.append(lines[i].strip());i+=1
        story.append(para(' '.join(paragraph)))
    GuideDoc().multiBuild(story)
    print(OUTPUT)
    print(f'{OUTPUT.stat().st_size:,} bytes')


if __name__=='__main__':
    main()
