from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


OUT_PATH = Path("/Users/saichandc/Documents/Test/Listojo_Business_Analysis_Deck_Visual.pptx")


def xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def content_types_xml(slide_count: int) -> str:
    overrides = [
        ("/ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
        ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
        ("/ppt/slideMasters/slideMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"),
        ("/ppt/slideLayouts/slideLayout1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"),
        ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml"),
    ]
    for i in range(1, slide_count + 1):
        overrides.append(
            (f"/ppt/slides/slide{i}.xml", "application/vnd.openxmlformats-officedocument.presentationml.slide+xml")
        )
    body = [
        xml_header(),
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    for part, content_type in overrides:
        body.append(f'<Override PartName="{part}" ContentType="{content_type}"/>')
    body.append("</Types>")
    return "".join(body)


def root_rels_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>',
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>',
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>',
            '</Relationships>',
        ]
    )


def app_xml(slide_count: int) -> str:
    return "".join(
        [
            xml_header(),
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" ',
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">',
            '<Application>Microsoft Office PowerPoint</Application>',
            '<PresentationFormat>On-screen Show (16:9)</PresentationFormat>',
            f"<Slides>{slide_count}</Slides>",
            '<Notes>0</Notes><HiddenSlides>0</HiddenSlides><MMClips>0</MMClips>',
            '<ScaleCrop>false</ScaleCrop>',
            '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Theme</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>',
            '<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>Office Theme</vt:lpstr></vt:vector></TitlesOfParts>',
            '<Company>OpenAI Codex</Company>',
            '<LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion>',
            '</Properties>',
        ]
    )


def core_xml() -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "".join(
        [
            xml_header(),
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" ',
            'xmlns:dc="http://purl.org/dc/elements/1.1/" ',
            'xmlns:dcterms="http://purl.org/dc/terms/" ',
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" ',
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
            '<dc:title>Listojo Business Analysis Deck</dc:title>',
            '<dc:creator>OpenAI Codex</dc:creator>',
            '<cp:lastModifiedBy>OpenAI Codex</cp:lastModifiedBy>',
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>',
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>',
            '</cp:coreProperties>',
        ]
    )


def presentation_xml(slide_count: int) -> str:
    sld_ids = [f'<p:sldId id="{256 + i}" r:id="rId{i + 1}"/>' for i in range(1, slide_count + 1)]
    return "".join(
        [
            xml_header(),
            '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ',
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">',
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>',
            '<p:sldIdLst>',
            "".join(sld_ids),
            '</p:sldIdLst>',
            '<p:sldSz cx="12192000" cy="6858000"/>',
            '<p:notesSz cx="6858000" cy="9144000"/>',
            '<p:defaultTextStyle><a:defPPr/><a:lvl1pPr marL="0" indent="0"><a:defRPr sz="2000"/></a:lvl1pPr></p:defaultTextStyle>',
            '</p:presentation>',
        ]
    )


def presentation_rels_xml(slide_count: int) -> str:
    rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    ]
    for i in range(1, slide_count + 1):
        rels.append(
            f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        )
    return "".join(
        [
            xml_header(),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            "".join(rels),
            '</Relationships>',
        ]
    )


def slide_master_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ',
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">',
            '<p:cSld name="Office Theme"><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg><p:spTree>',
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>',
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>',
            '</p:spTree></p:cSld>',
            '<p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/>',
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>',
            '<p:txStyles><p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="2800" b="1"/></a:lvl1pPr></p:titleStyle><p:bodyStyle><a:lvl1pPr marL="0" indent="0"><a:defRPr sz="2000"/></a:lvl1pPr></p:bodyStyle><p:otherStyle><a:defPPr/></p:otherStyle></p:txStyles>',
            '</p:sldMaster>',
        ]
    )


def slide_master_rels_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>',
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>',
            '</Relationships>',
        ]
    )


def slide_layout_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ',
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">',
            '<p:cSld name="Blank"><p:spTree>',
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>',
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>',
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>',
        ]
    )


def slide_layout_rels_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>',
            '</Relationships>',
        ]
    )


def theme_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Listojo Theme">',
            '<a:themeElements>',
            '<a:clrScheme name="Listojo Colors">',
            '<a:dk1><a:srgbClr val="0F1C35"/></a:dk1>',
            '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>',
            '<a:dk2><a:srgbClr val="1F2937"/></a:dk2>',
            '<a:lt2><a:srgbClr val="F8FAFC"/></a:lt2>',
            '<a:accent1><a:srgbClr val="2A7EF2"/></a:accent1>',
            '<a:accent2><a:srgbClr val="3DB549"/></a:accent2>',
            '<a:accent3><a:srgbClr val="F59E0B"/></a:accent3>',
            '<a:accent4><a:srgbClr val="62C2FF"/></a:accent4>',
            '<a:accent5><a:srgbClr val="E11D48"/></a:accent5>',
            '<a:accent6><a:srgbClr val="64748B"/></a:accent6>',
            '<a:hlink><a:srgbClr val="2563EB"/></a:hlink>',
            '<a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>',
            '</a:clrScheme>',
            '<a:fontScheme name="Listojo Fonts">',
            '<a:majorFont><a:latin typeface="Aptos Display"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>',
            '<a:minorFont><a:latin typeface="Aptos"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>',
            '</a:fontScheme>',
            '<a:fmtScheme name="Listojo Format"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="lt1"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>',
            '</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/>',
            '</a:theme>',
        ]
    )


def para_xml(text: str, *, bullet: bool = False, size: int = 1900, bold: bool = False, color: str = "1F2937") -> str:
    ppr = "<a:pPr>" + ('<a:buChar char="•"/>' if bullet else "<a:buNone/>") + "</a:pPr>"
    b = ' b="1"' if bold else ""
    return (
        f'<a:p>{ppr}<a:r><a:rPr lang="en-US" sz="{size}"{b}>'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
        f"<a:t>{escape(text)}</a:t></a:r><a:endParaRPr lang=\"en-US\" sz=\"{size}\"/></a:p>"
    )


def textbox_xml(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paragraphs: str) -> str:
    return "".join(
        [
            f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>',
            '<p:spPr><a:xfrm>',
            f'<a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>',
            '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>',
            '<p:txBody><a:bodyPr wrap="square" rtlCol="0" anchor="t"/><a:lstStyle/>',
            paragraphs,
            '</p:txBody></p:sp>',
        ]
    )


def rect_xml(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, fill: str, line: str | None = None, radius: str = "roundRect") -> str:
    if line:
        line_xml = f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>'
    else:
        line_xml = '<a:ln><a:noFill/></a:ln>'
    return "".join(
        [
            f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>',
            '<p:spPr><a:xfrm>',
            f'<a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>',
            f'</a:xfrm><a:prstGeom prst="{radius}"><a:avLst/></a:prstGeom>',
            f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>',
            line_xml,
            '</p:spPr></p:sp>',
        ]
    )


def line_xml(shape_id: int, x1: int, y1: int, x2: int, y2: int, color: str = "CBD5E1", width: int = 19050) -> str:
    return "".join(
        [
            f'<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="{shape_id}" name="Line {shape_id}"/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr>',
            '<p:spPr><a:xfrm>',
            f'<a:off x="{x1}" y="{y1}"/><a:ext cx="{x2 - x1}" cy="{y2 - y1}"/>',
            '</a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom>',
            f'<a:ln w="{width}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln>',
            '</p:spPr></p:cxnSp>',
        ]
    )


def add_title(shapes: list[str], title: str, subtitle: str | None = None) -> None:
    shapes.append(rect_xml(2, "AccentBar", 0, 0, 12192000, 228600, "2A7EF2", None, "rect"))
    shapes.append(
        textbox_xml(3, "Title", 609600, 365760, 10972800, 640080, para_xml(title, size=2800, bold=True, color="0F1C35"))
    )
    if subtitle:
        shapes.append(
            textbox_xml(4, "Subtitle", 609600, 1028700, 10972800, 411480, para_xml(subtitle, size=1600, color="475569"))
        )


def build_cover_slide() -> str:
    shapes: list[str] = []
    shapes.append(rect_xml(2, "Top", 0, 0, 12192000, 6858000, "F8FAFC", None, "rect"))
    shapes.append(rect_xml(3, "BluePanel", 0, 0, 4064000, 6858000, "0F1C35", None, "rect"))
    shapes.append(rect_xml(4, "Circle1", 284000, 620000, 1500000, 1500000, "1D4ED8", None, "ellipse"))
    shapes.append(rect_xml(5, "Circle2", 1010000, 1880000, 1120000, 1120000, "3DB549", None, "ellipse"))
    shapes.append(rect_xml(6, "Circle3", 760000, 3480000, 1360000, 1360000, "62C2FF", None, "ellipse"))
    shapes.append(
        textbox_xml(
            7,
            "SideTitle",
            480000,
            4850000,
            3000000,
            900000,
            para_xml("Business Analyst Review", size=2200, bold=True, color="FFFFFF")
            + para_xml("Listojo Marketplace", size=1800, color="DCEAFE"),
        )
    )
    shapes.append(
        textbox_xml(
            8,
            "MainTitle",
            4500000,
            1050000,
            6800000,
            1000000,
            para_xml("Listojo", size=3200, bold=True, color="0F1C35")
            + para_xml("Business Analysis Deck", size=2600, bold=True, color="0F1C35"),
        )
    )
    shapes.append(
        textbox_xml(
            9,
            "Subtitle",
            4500000,
            2150000,
            6400000,
            1100000,
            para_xml("Whole-chat summary converted into a presentation with visuals, graphs, and strategic recommendations.", size=1700, color="475569"),
        )
    )
    shapes.append(rect_xml(10, "Chip1", 4500000, 3600000, 1900000, 520000, "DBEAFE", None))
    shapes.append(rect_xml(11, "Chip2", 6600000, 3600000, 1900000, 520000, "DCFCE7", None))
    shapes.append(rect_xml(12, "Chip3", 8700000, 3600000, 2100000, 520000, "FEF3C7", None))
    shapes.append(textbox_xml(13, "Chip1Text", 4680000, 3720000, 1600000, 300000, para_xml("Product Review", size=1500, bold=True, color="1E3A8A")))
    shapes.append(textbox_xml(14, "Chip2Text", 6780000, 3720000, 1600000, 300000, para_xml("Revenue Logic", size=1500, bold=True, color="166534")))
    shapes.append(textbox_xml(15, "Chip3Text", 8880000, 3720000, 1800000, 300000, para_xml("GTM & Risks", size=1500, bold=True, color="92400E")))
    return slide_xml_from_shapes(shapes)


def build_exec_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Executive Summary", "High-level business reading of the product and the discussion")
    card_specs = [
        (2_000_000, "Promising MVP", "Real working marketplace, not just a front-end mockup.", "DBEAFE", "1E3A8A"),
        (4_600_000, "Best Wedge", "DFW rentals for small self-managed landlords and renters.", "DCFCE7", "166534"),
        (7_200_000, "Current State", "Pre-PMF with meaningful validation potential, but not scale-ready.", "FEF3C7", "92400E"),
    ]
    sid = 20
    for x, title, body, fill, color in card_specs:
        shapes.append(rect_xml(sid, title, x, 1850000, 2100000, 1750000, fill, None))
        shapes.append(textbox_xml(sid + 1, title + "T", x + 180000, 2010000, 1700000, 300000, para_xml(title, size=1800, bold=True, color=color)))
        shapes.append(textbox_xml(sid + 2, title + "B", x + 180000, 2400000, 1700000, 980000, para_xml(body, size=1450, color="334155")))
        sid += 3
    bullets = (
        para_xml("Core workflows already exist: listings, search, favorites, inquiries, chat, and admin visibility.", bullet=True)
        + para_xml("Biggest near-term challenge is liquidity and trust, not feature count.", bullet=True)
        + para_xml("Best next step is disciplined local validation before monetization or expansion.", bullet=True)
    )
    shapes.append(textbox_xml(40, "Bullets", 1200000, 4100000, 9800000, 1800000, bullets))
    return slide_xml_from_shapes(shapes)


def build_value_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Current Product Value", "Who benefits today and why the product can create real utility")
    cols = [
        ("Small Landlords", "Free listing channel with simpler posting and local relevance.", "DBEAFE", "1E3A8A"),
        ("Renters", "Guided discovery and a more structured search experience.", "DCFCE7", "166534"),
        ("Founder / Operator", "Useful platform for market learning, operational testing, and supply seeding.", "FCE7F3", "9D174D"),
    ]
    sid = 20
    x = 900000
    for title, body, fill, color in cols:
        shapes.append(rect_xml(sid, title, x, 1900000, 3200000, 1400000, fill, None))
        shapes.append(textbox_xml(sid + 1, title + "T", x + 220000, 2080000, 2600000, 300000, para_xml(title, size=1900, bold=True, color=color)))
        shapes.append(textbox_xml(sid + 2, title + "B", x + 220000, 2500000, 2600000, 760000, para_xml(body, size=1500, color="334155")))
        x += 3600000
        sid += 3
    bullets = (
        para_xml("The product creates the most value when positioned narrowly as a trusted local rental marketplace.", bullet=True)
        + para_xml("In a controlled pilot city, the implemented feature set is enough to test real demand and supply behavior.", bullet=True)
    )
    shapes.append(textbox_xml(40, "Bottom", 1100000, 4100000, 9800000, 1300000, bullets))
    return slide_xml_from_shapes(shapes)


def build_score_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Overall Product Rating", "Score-based view of product quality and business readiness")
    metrics = [
        ("Product concept", 7.5, "2A7EF2"),
        ("User value in local launch", 6.0, "3DB549"),
        ("Commercial readiness", 4.0, "F59E0B"),
        ("Operational readiness for scale", 3.0, "E11D48"),
    ]
    sid = 20
    y = 1800000
    for label, score, color in metrics:
        shapes.append(textbox_xml(sid, label, 1000000, y, 2600000, 280000, para_xml(label, size=1700, bold=True, color="0F172A")))
        shapes.append(rect_xml(sid + 1, label + "Track", 3900000, y + 30000, 5200000, 220000, "E2E8F0", None, "rect"))
        shapes.append(rect_xml(sid + 2, label + "Fill", 3900000, y + 30000, int(5200000 * (score / 10.0)), 220000, color, None, "rect"))
        shapes.append(textbox_xml(sid + 3, label + "Score", 9400000, y - 20000, 1200000, 280000, para_xml(f"{score:.1f} / 10", size=1700, bold=True, color=color)))
        y += 780000
        sid += 4
    shapes.append(
        textbox_xml(
            50,
            "Callout",
            1000000,
            5200000,
            9800000,
            700000,
            para_xml("Interpretation: strong enough for a local validation launch, but too early for broad scale or hard monetization.", size=1650, color="475569"),
        )
    )
    return slide_xml_from_shapes(shapes)


def build_good_bad_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "What Is Good vs. What Is Weak", "Balanced view of the product’s commercial strengths and limitations")
    shapes.append(rect_xml(20, "Good", 900000, 1800000, 4700000, 3600000, "ECFDF5", "86EFAC"))
    shapes.append(rect_xml(21, "Weak", 6400000, 1800000, 4700000, 3600000, "FEF2F2", "FCA5A5"))
    shapes.append(textbox_xml(22, "GoodT", 1160000, 1980000, 2200000, 320000, para_xml("Good", size=2200, bold=True, color="166534")))
    shapes.append(textbox_xml(23, "WeakT", 6660000, 1980000, 2200000, 320000, para_xml("Weak", size=2200, bold=True, color="991B1B")))
    good = (
        para_xml("Clear local wedge market", bullet=True)
        + para_xml("Real marketplace workflow already built", bullet=True)
        + para_xml("Guided search and matching create differentiation", bullet=True)
        + para_xml("Portal/dashboard supports early operations", bullet=True)
    )
    weak = (
        para_xml("Low liquidity risk at launch", bullet=True)
        + para_xml("Trust signals not yet strong enough", bullet=True)
        + para_xml("Monetization is earlier in theory than in practice", bullet=True)
        + para_xml("Scaling and QA maturity remain weak", bullet=True)
    )
    shapes.append(textbox_xml(24, "GoodB", 1160000, 2380000, 4000000, 2400000, good))
    shapes.append(textbox_xml(25, "WeakB", 6660000, 2380000, 4000000, 2400000, weak))
    return slide_xml_from_shapes(shapes)


def build_risk_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Top Business Risks", "Risk heat view based on the business discussion")
    risks = [
        ("Liquidity", "Very High", "DC2626", 88),
        ("Trust / Moderation", "High", "EA580C", 74),
        ("Positioning Dilution", "Medium", "F59E0B", 58),
        ("Premature Monetization", "Medium", "F59E0B", 54),
        ("Founder-Heavy Ops", "Medium", "EAB308", 50),
    ]
    sid = 20
    y = 1800000
    for label, lvl, color, pct in risks:
        shapes.append(textbox_xml(sid, label, 900000, y, 2500000, 260000, para_xml(label, size=1650, bold=True, color="0F172A")))
        shapes.append(rect_xml(sid + 1, label + "Track", 3600000, y + 20000, 5000000, 200000, "E2E8F0", None, "rect"))
        shapes.append(rect_xml(sid + 2, label + "Fill", 3600000, y + 20000, int(5000000 * pct / 100), 200000, color, None, "rect"))
        shapes.append(textbox_xml(sid + 3, label + "Level", 8950000, y - 10000, 1700000, 260000, para_xml(lvl, size=1550, bold=True, color=color)))
        y += 700000
        sid += 4
    return slide_xml_from_shapes(shapes)


def build_sweat_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "SWOT Analysis", "Structured view of strategic position")
    quads = [
        (900000, 1750000, "Strengths", "DBEAFE", "1E3A8A", ["Focused wedge", "Real workflow", "Guided search", "Admin visibility"]),
        (6400000, 1750000, "Weaknesses", "FEE2E2", "991B1B", ["Low scale readiness", "Trust layer incomplete", "Broad story", "Monetization immature"]),
        (900000, 4000000, "Opportunities", "DCFCE7", "166534", ["Own small-landlord niche", "Verification layer", "Paid boosts", "City expansion playbook"]),
        (6400000, 4000000, "Threats", "FEF3C7", "92400E", ["Incumbent density", "Cold-start failure", "Early trust erosion", "Premature charging"]),
    ]
    sid = 20
    for x, y, title, fill, color, items in quads:
        shapes.append(rect_xml(sid, title, x, y, 4700000, 1800000, fill, None))
        shapes.append(textbox_xml(sid + 1, title + "T", x + 180000, y + 140000, 2000000, 280000, para_xml(title, size=1900, bold=True, color=color)))
        paragraphs = "".join(para_xml(item, bullet=True, size=1450, color="334155") for item in items)
        shapes.append(textbox_xml(sid + 2, title + "B", x + 180000, y + 470000, 4100000, 1100000, paragraphs))
        sid += 3
    return slide_xml_from_shapes(shapes)


def build_pmf_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Product-Market Fit Scorecard", "Quantified reading of PMF readiness")
    metrics = [
        ("Problem clarity", 8.0),
        ("Target user definition", 7.0),
        ("Core usefulness", 6.5),
        ("Differentiation", 7.0),
        ("Trust readiness", 4.5),
        ("Liquidity readiness", 4.0),
        ("Monetization readiness", 4.0),
        ("Operational readiness", 4.0),
    ]
    sid = 20
    y = 1700000
    for label, score in metrics:
        color = "3DB549" if score >= 7 else "F59E0B" if score >= 5 else "E11D48"
        shapes.append(textbox_xml(sid, label, 800000, y, 2600000, 220000, para_xml(label, size=1450, bold=True, color="0F172A")))
        shapes.append(rect_xml(sid + 1, label + "Track", 3400000, y + 20000, 3900000, 160000, "E2E8F0", None, "rect"))
        shapes.append(rect_xml(sid + 2, label + "Fill", 3400000, y + 20000, int(3900000 * score / 10.0), 160000, color, None, "rect"))
        shapes.append(textbox_xml(sid + 3, label + "Score", 7700000, y - 10000, 1200000, 220000, para_xml(f"{score:.1f}", size=1450, bold=True, color=color)))
        y += 520000
        sid += 4
    shapes.append(rect_xml(80, "TotalBox", 9300000, 2200000, 1800000, 1800000, "EFF6FF", "93C5FD"))
    shapes.append(textbox_xml(81, "TotalT", 9580000, 2420000, 1250000, 350000, para_xml("Overall", size=1700, bold=True, color="1E3A8A")))
    shapes.append(textbox_xml(82, "TotalS", 9580000, 2870000, 1250000, 450000, para_xml("5.4 / 10", size=2200, bold=True, color="1E3A8A")))
    shapes.append(textbox_xml(83, "TotalB", 9480000, 3470000, 1450000, 500000, para_xml("Pre-PMF but credible", size=1450, color="475569")))
    return slide_xml_from_shapes(shapes)


def build_revenue_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Revenue Logic", "Commercial levers ranked by practicality and timing")
    labels = [
        ("Paid boosts", 90, "2A7EF2"),
        ("Verification", 74, "3DB549"),
        ("Premium landlord tools", 68, "62C2FF"),
        ("Screening / services", 55, "F59E0B"),
        ("Agent lead routing", 46, "E11D48"),
    ]
    base_x = 1300000
    bar_w = 1200000
    gap = 750000
    sid = 20
    for idx, (label, height_pct, color) in enumerate(labels):
        x = base_x + idx * (bar_w + gap)
        h = int(2200000 * height_pct / 100)
        y = 4700000 - h
        shapes.append(rect_xml(sid, label + "Bar", x, y, bar_w, h, color, None, "rect"))
        shapes.append(textbox_xml(sid + 1, label + "Pct", x, y - 260000, bar_w, 220000, para_xml(f"{height_pct}", size=1450, bold=True, color=color)))
        shapes.append(textbox_xml(sid + 2, label + "Lbl", x - 180000, 4900000, bar_w + 360000, 620000, para_xml(label, size=1300, bold=True, color="334155")))
        sid += 3
    shapes.append(line_xml(100, 1100000, 4700000, 10500000, 4700000))
    shapes.append(
        textbox_xml(
            101,
            "Foot",
            1100000,
            5550000,
            9800000,
            550000,
            para_xml("Interpretation: featured/boosted placement is the cleanest first revenue stream, but only after supply quality and landlord outcomes are proven.", size=1500, color="475569"),
        )
    )
    return slide_xml_from_shapes(shapes)


def build_pricing_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Pricing Roadmap", "Recommended commercial sequencing")
    xs = [900000, 3600000, 6300000, 9000000]
    cards = [
        ("1", "Free Core", "Free listing, inquiry, chat, and photos to build supply.", "DBEAFE", "1E3A8A"),
        ("2", "Paid Boosts", "Weekly visibility products once landlords are getting real leads.", "DCFCE7", "166534"),
        ("3", "Premium Tools", "Analytics, renewals, portfolio tools, and workflow upgrades.", "E0F2FE", "0C4A6E"),
        ("4", "Services", "Verification, screening, and partner revenue once trust grows.", "FEF3C7", "92400E"),
    ]
    sid = 20
    for x, (num, title, body, fill, color) in zip(xs, cards):
        shapes.append(rect_xml(sid, title, x, 2200000, 1900000, 2200000, fill, None))
        shapes.append(rect_xml(sid + 1, title + "Bubble", x + 700000, 1900000, 500000, 500000, color, None, "ellipse"))
        shapes.append(textbox_xml(sid + 2, title + "N", x + 880000, 2020000, 160000, 160000, para_xml(num, size=1500, bold=True, color="FFFFFF")))
        shapes.append(textbox_xml(sid + 3, title + "T", x + 180000, 2820000, 1500000, 280000, para_xml(title, size=1700, bold=True, color=color)))
        shapes.append(textbox_xml(sid + 4, title + "B", x + 180000, 3240000, 1500000, 880000, para_xml(body, size=1350, color="334155")))
        sid += 5
    shapes.append(line_xml(80, 2800000, 3300000, 3600000, 3300000, "94A3B8"))
    shapes.append(line_xml(81, 5500000, 3300000, 6300000, 3300000, "94A3B8"))
    shapes.append(line_xml(82, 8200000, 3300000, 9000000, 3300000, "94A3B8"))
    return slide_xml_from_shapes(shapes)


def build_gtm_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Go-To-Market Recommendation", "Best launch path based on the business discussion")
    shapes.append(rect_xml(20, "Center", 4200000, 2550000, 3800000, 1200000, "DBEAFE", "93C5FD"))
    shapes.append(textbox_xml(21, "CenterT", 4460000, 2870000, 3200000, 420000, para_xml("DFW Rentals for Small Landlords", size=2200, bold=True, color="1E3A8A")))
    spokes = [
        (1400000, 1650000, "Supply Seeding"),
        (9000000, 1650000, "Local Channels"),
        (1400000, 4300000, "Trust First"),
        (9000000, 4300000, "Landlord Metrics"),
    ]
    sid = 30
    for x, y, text in spokes:
        shapes.append(rect_xml(sid, text, x, y, 2200000, 800000, "F8FAFC", "CBD5E1"))
        shapes.append(textbox_xml(sid + 1, text + "T", x + 140000, y + 220000, 1900000, 280000, para_xml(text, size=1700, bold=True, color="334155")))
        sid += 2
    shapes.append(line_xml(50, 3600000, 2450000, 4200000, 2900000, "94A3B8"))
    shapes.append(line_xml(51, 8000000, 2900000, 9000000, 2450000, "94A3B8"))
    shapes.append(line_xml(52, 3600000, 4700000, 4200000, 3600000, "94A3B8"))
    shapes.append(line_xml(53, 8000000, 3600000, 9000000, 4700000, "94A3B8"))
    return slide_xml_from_shapes(shapes)


def build_reco_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Top 5 Immediate Recommendations", "Highest-leverage actions to increase business value")
    recos = [
        "Narrow the story to DFW rentals first",
        "Strengthen trust and moderation before adding more breadth",
        "Make guided search measurably improve outcomes",
        "Track landlord success as the primary KPI",
        "Delay aggressive monetization until lead quality is proven",
    ]
    sid = 20
    y = 1700000
    colors = ["DBEAFE", "DCFCE7", "E0F2FE", "FEF3C7", "FCE7F3"]
    text_colors = ["1E3A8A", "166534", "0C4A6E", "92400E", "9D174D"]
    for i, reco in enumerate(recos, start=1):
        shapes.append(rect_xml(sid, reco, 1200000, y, 9800000, 520000, colors[i - 1], None))
        shapes.append(rect_xml(sid + 1, f"Num{i}", 1400000, y + 80000, 340000, 340000, text_colors[i - 1], None, "ellipse"))
        shapes.append(textbox_xml(sid + 2, f"NumText{i}", 1530000, y + 145000, 120000, 140000, para_xml(str(i), size=1350, bold=True, color="FFFFFF")))
        shapes.append(textbox_xml(sid + 3, f"Reco{i}", 1900000, y + 120000, 8500000, 220000, para_xml(reco, size=1550, bold=True, color="334155")))
        sid += 4
        y += 760000
    return slide_xml_from_shapes(shapes)


def build_final_slide() -> str:
    shapes: list[str] = []
    add_title(shapes, "Final Assessment", "Bottom-line conclusion from the full business discussion")
    shapes.append(rect_xml(20, "Main", 1200000, 1900000, 9800000, 2500000, "EFF6FF", "93C5FD"))
    summary = (
        para_xml("Listojo is promising, not broken.", size=2000, bold=True, color="1E3A8A")
        + para_xml("It is good enough for a controlled local validation launch.", bullet=True)
        + para_xml("It is not yet mature enough for broad rollout or hard monetization.", bullet=True)
        + para_xml("If supply, trust, and repeat landlord value are proven in one city, the business can become meaningful.", bullet=True)
        + para_xml("If those signals do not appear, more features alone will not solve the core business problem.", bullet=True)
    )
    shapes.append(textbox_xml(21, "Summary", 1600000, 2250000, 9000000, 1800000, summary))
    shapes.append(rect_xml(22, "TagA", 2600000, 4900000, 1800000, 420000, "DBEAFE", None))
    shapes.append(rect_xml(23, "TagB", 4950000, 4900000, 1800000, 420000, "DCFCE7", None))
    shapes.append(rect_xml(24, "TagC", 7300000, 4900000, 1800000, 420000, "FEF3C7", None))
    shapes.append(textbox_xml(25, "TagAT", 2870000, 5010000, 1300000, 180000, para_xml("Validate", size=1400, bold=True, color="1E3A8A")))
    shapes.append(textbox_xml(26, "TagBT", 5230000, 5010000, 1300000, 180000, para_xml("Build Trust", size=1400, bold=True, color="166534")))
    shapes.append(textbox_xml(27, "TagCT", 7600000, 5010000, 1300000, 180000, para_xml("Monetize Later", size=1400, bold=True, color="92400E")))
    return slide_xml_from_shapes(shapes)


def slide_xml_from_shapes(shapes: list[str]) -> str:
    return "".join(
        [
            xml_header(),
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ',
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">',
            '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="F8FAFC"/></a:solidFill></p:bgPr></p:bg><p:spTree>',
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>',
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>',
            "".join(shapes),
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>',
        ]
    )


def slide_rels_xml() -> str:
    return "".join(
        [
            xml_header(),
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>',
            '</Relationships>',
        ]
    )


SLIDES = [
    build_cover_slide,
    build_exec_slide,
    build_value_slide,
    build_score_slide,
    build_good_bad_slide,
    build_risk_slide,
    build_sweat_slide,
    build_pmf_slide,
    build_revenue_slide,
    build_pricing_slide,
    build_gtm_slide,
    build_reco_slide,
    build_final_slide,
]


def build_pptx(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    slide_count = len(SLIDES)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml(slide_count))
        zf.writestr("_rels/.rels", root_rels_xml())
        zf.writestr("docProps/app.xml", app_xml(slide_count))
        zf.writestr("docProps/core.xml", core_xml())
        zf.writestr("ppt/presentation.xml", presentation_xml(slide_count))
        zf.writestr("ppt/_rels/presentation.xml.rels", presentation_rels_xml(slide_count))
        zf.writestr("ppt/slideMasters/slideMaster1.xml", slide_master_xml())
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", slide_master_rels_xml())
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", slide_layout_xml())
        zf.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", slide_layout_rels_xml())
        zf.writestr("ppt/theme/theme1.xml", theme_xml())
        for idx, slide_fn in enumerate(SLIDES, start=1):
            zf.writestr(f"ppt/slides/slide{idx}.xml", slide_fn())
            zf.writestr(f"ppt/slides/_rels/slide{idx}.xml.rels", slide_rels_xml())


if __name__ == "__main__":
    build_pptx(OUT_PATH)
    print(OUT_PATH)
