from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


OUT_PATH = Path("/Users/saichandc/Documents/Test/Listojo_Business_Logic_Flow_Diagram.docx")


CONTENT = """Business Logic Flow Diagram

Title
Listojo Business Logic Flow

Subtitle
How user discovery converts into lead capture, agent engagement, and referral value

Executive Summary
Listojo operates as a hybrid self-serve and agent-assisted discovery platform. Users can browse and receive curated results on their own, while the platform captures structured intent as lead data. When the user explicitly requests help or shows higher intent later, the lead can be routed to an agent for shortlist creation, follow-up, and conversion. Business value is realized through referral revenue, demand intelligence, and funnel visibility.

Polished Pictorial Box-and-Arrow Diagram

+-----------------------+
| 1. USER ENTRY         |
+-----------------------+
| User lands on Listojo |
| to find a home,       |
| rental, or listing    |
+-----------+-----------+
            |
            v
+------------------------------+
| 2. DISCOVERY PATH            |
+------------------------------+
| Guided search                |
| Direct listing browse        |
| Direct listing inquiry       |
+-----------+------------------+
            |
            v
+------------------------------+
| 3. INTENT CAPTURE            |
+------------------------------+
| Platform captures:           |
| City                         |
| Budget                       |
| Bedrooms                     |
| Move-in timing               |
| Amenities / preferences      |
+-----------+------------------+
            |
            v
+------------------------------+
| 4. LEAD CREATION             |
+------------------------------+
| Internal lead created or     |
| updated with preferences     |
| for future follow-up         |
+-----------+------------------+
            |
            v
+------------------------------+
| 5. CURATED RESULTS           |
+------------------------------+
| User receives matched        |
| listings and shortlist-like  |
| recommendations              |
+-----------+------------------+
            |
            v
      /----------------------\\
     / 6. NEED AGENT HELP?   \\
     \\ User decision         /
      \\----------+-----------/
                 / \\
                /   \\
               v     v
+------------------+   +---------------------------+
| 7A. SELF-SERVE   |   | 7B. AGENT ENGAGEMENT     |
+------------------+   +---------------------------+
| User continues   |   | Lead is assigned to      |
| browsing without |   | an agent for follow-up   |
| agent support    |   | and guided assistance    |
+--------+---------+   +------------+--------------+
         |                          |
         v                          v
   /----------------\\      +----------------------------+
  / High Intent      \\     | 8. AGENT WORKFLOW         |
 / Later?            /     +----------------------------+
 \\-------+----------/      | Review lead               |
  \\      |                 | Understand preferences    |
   \\     |                 | Create shortlist          |
    v    v                 | Follow up with user       |
+----------+               | Guide tour / next steps   |
| Re-route |               +------------+---------------+
| to agent |                            |
+----+-----+                            v
     |                      +----------------------------+
     +--------------------> | 9. OUTCOME                |
                            +----------------------------+
                            | Tour / engagement         |
                            | Nurture / no response     |
                            | Closed lost               |
                            | Closed won                |
                            +------------+---------------+
                                         |
                                         v
                            +----------------------------+
                            | 10. BUSINESS VALUE         |
                            +----------------------------+
                            | Referral revenue           |
                            | Lead intelligence          |
                            | Demand analytics           |
                            | Agent performance tracking |
                            +----------------------------+

Business Stage Labels
1. User Entry
2. Discovery Path
3. Intent Capture
4. Lead Creation
5. Curated Results
6. Agent Help Decision
7A. Self-Serve Journey
7B. Agent Engagement
8. Agent Workflow
9. Outcome
10. Business Value

Key Decision Logic
- Guided search and browsing are the top-of-funnel discovery actions.
- Platform captures structured intent and stores it as lead data.
- User can stay self-serve or explicitly ask for agent help.
- Self-serve users can still be escalated later if they show higher intent.
- Agent workflow is the conversion engine.
- Revenue is realized only when qualified demand converts into an attributable referral or agent-assisted outcome.

Recommended Slide Callouts

Self-Serve Logic
- User can receive immediate value without agent involvement.
- Platform remains useful even before agent escalation.
- This reduces friction and supports organic discovery.

Agent Monetization Logic
- Agent help is triggered by explicit request or later high-intent behavior.
- Assigned agent reviews the lead, builds a shortlist, and follows up.
- Business value comes from conversion tracking, referral outcomes, and funnel intelligence.

Footer Insight
Core business model: capture demand, curate options, enable optional agent assistance, and monetize through conversion-driven referral outcomes.
"""


def xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def content_types_xml() -> str:
    return "".join([
        xml_header(),
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
        '</Types>',
    ])


def root_rels_xml() -> str:
    return "".join([
        xml_header(),
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>',
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>',
        '</Relationships>',
    ])


def app_xml() -> str:
    return "".join([
        xml_header(),
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" ',
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">',
        '<Application>Microsoft Office Word</Application>',
        '<DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>',
        '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Title</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>',
        '<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>Document</vt:lpstr></vt:vector></TitlesOfParts>',
        '<Company>OpenAI Codex</Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion>',
        '</Properties>',
    ])


def core_xml() -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "".join([
        xml_header(),
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" ',
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" ',
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        '<dc:title>Listojo Business Logic Flow Diagram</dc:title>',
        '<dc:creator>OpenAI Codex</dc:creator>',
        '<cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>',
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>',
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>',
        '</cp:coreProperties>',
    ])


def word_rels_xml() -> str:
    return "".join([
        xml_header(),
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
        '</Relationships>',
    ])


def styles_xml() -> str:
    return "".join([
        xml_header(),
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:rPr><w:sz w:val="22"/></w:rPr></w:style>',
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>',
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>',
        '</w:styles>',
    ])


def paragraph_xml(text: str, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def document_xml() -> str:
    parts = [paragraph_xml("Listojo Business Logic Flow Diagram", style="Title"), paragraph_xml("")]
    for line in CONTENT.splitlines():
        parts.append(paragraph_xml(line))
    parts.append('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    return "".join([
        xml_header(),
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" ',
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" ',
        'xmlns:o="urn:schemas-microsoft-com:office:office" ',
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" ',
        'xmlns:v="urn:schemas-microsoft-com:vml" ',
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" ',
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" ',
        'xmlns:w10="urn:schemas-microsoft-com:office:word" ',
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ',
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" ',
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" ',
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" ',
        'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" ',
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 wp14">',
        "<w:body>", "".join(parts), "</w:body></w:document>",
    ])


def build_docx(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml())
        zf.writestr("_rels/.rels", root_rels_xml())
        zf.writestr("docProps/app.xml", app_xml())
        zf.writestr("docProps/core.xml", core_xml())
        zf.writestr("word/document.xml", document_xml())
        zf.writestr("word/styles.xml", styles_xml())
        zf.writestr("word/_rels/document.xml.rels", word_rels_xml())


if __name__ == "__main__":
    build_docx(OUT_PATH)
    print(OUT_PATH)
