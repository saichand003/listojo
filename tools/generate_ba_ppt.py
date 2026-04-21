from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


OUT_PATH = Path("/Users/saichandc/Documents/Test/Listojo_Business_Analysis_Deck.pptx")


SLIDES = [
    {
        "title": "Listojo Business Analysis",
        "subtitle": "Product review, value assessment, risks, monetization, and go-to-market recommendations",
        "bullets": [
            "Prepared as a business analyst review of the current codebase and implemented features",
            "Focus: product quality, commercial potential, user value, key flaws, and revenue logic",
            "Conclusion: promising local marketplace MVP, but still pre-product-market-fit",
        ],
    },
    {
        "title": "Executive Summary",
        "bullets": [
            "Listojo is a real working marketplace MVP, not just a UI demo.",
            "The strongest wedge is DFW rentals for small self-managed landlords and renters.",
            "Core flows already exist: listing creation, search, favourites, inquiries, chat, and admin portal.",
            "Best near-term use: validate one local market before broader expansion or monetization.",
            "Main weakness: trust, liquidity, and monetization maturity lag behind the product story.",
        ],
    },
    {
        "title": "Current Product Value",
        "bullets": [
            "Useful for small landlords who want free exposure without large listing fees.",
            "Useful for renters who want more guided discovery than Craigslist or Facebook Marketplace.",
            "Guided search and matching logic create a stronger perceived intelligence layer than generic classifieds.",
            "The admin portal adds operational value by showing supply, engagement, and review workflow visibility.",
            "In a tightly managed pilot city, this product can create real user value today.",
        ],
    },
    {
        "title": "Overall Product Rating",
        "bullets": [
            "Product concept: 7.5 / 10",
            "User value for a controlled local launch: 6 / 10",
            "Commercial readiness: 4 / 10",
            "Operational readiness for scale: 3 / 10",
            "Overall read: promising MVP with validation potential, but not yet scale-ready.",
        ],
    },
    {
        "title": "What Is Working Well",
        "bullets": [
            "Clear local wedge market and easy-to-understand value proposition.",
            "More substantial than a normal CRUD MVP because it includes chat, saved listings, and funnel tracking.",
            "Guided search plus match explanations improve perceived sophistication.",
            "Portal/dashboard suggests the founder is thinking operationally, not only visually.",
            "DFW-first launch focus is strategically better than trying to launch broadly.",
        ],
    },
    {
        "title": "Top Business Risks",
        "bullets": [
            "Marketplace liquidity risk: too few listings will make search feel empty very quickly.",
            "Trust gap: the product promises a trusted experience, but moderation and verification are still early.",
            "Positioning dilution: broad classifieds framing is weaker than the actual rentals-first strength.",
            "Premature monetization risk: charging before clear landlord value is proven could choke supply.",
            "Founder-heavy operations risk: quality control and onboarding may still rely too much on manual effort.",
        ],
    },
    {
        "title": "Key Product Flaws",
        "bullets": [
            "The trust story appears stronger in strategy documents than in actual operating discipline.",
            "Category positioning is broader than the practical user flow, which creates message confusion.",
            "The flagship guided search experience is strong conceptually but still incomplete in business impact.",
            "Core workflows for landlord follow-up and response speed need to be more reliable.",
            "The product is polished enough to attract users, but not yet robust enough to keep both sides by default.",
        ],
    },
    {
        "title": "SWOT Analysis",
        "bullets": [
            "Strengths: focused local wedge, real marketplace workflow, guided search, admin visibility.",
            "Weaknesses: low scale readiness, incomplete trust layer, monetization not yet operationalized.",
            "Opportunities: own the small-landlord niche, build verification, add paid boosts and landlord tools.",
            "Threats: incumbents with inventory density, cold-start failure, early trust erosion, broad positioning.",
        ],
    },
    {
        "title": "Product-Market Fit Scorecard",
        "bullets": [
            "Problem clarity: 8 / 10",
            "Target user definition: 7 / 10",
            "Core product usefulness: 6.5 / 10",
            "Differentiation: 7 / 10",
            "Trust and quality readiness: 4.5 / 10",
            "Liquidity readiness: 4 / 10",
            "Monetization readiness: 4 / 10",
            "Overall PMF score: 5.4 / 10",
        ],
    },
    {
        "title": "Revenue Potential",
        "bullets": [
            "There is real monetization potential, but not yet strong pricing power.",
            "The most natural first lever is paid visibility: featured listings or listing boosts.",
            "Next best revenue layers are verification, premium landlord tools, and screening partnerships.",
            "The business should monetize trust, visibility, speed, and convenience, not basic participation.",
            "Revenue should follow proof of landlord outcomes, not precede it.",
        ],
    },
    {
        "title": "Recommended Pricing Roadmap",
        "bullets": [
            "Stage 1: Keep core listing, inquiry, and messaging free to build supply.",
            "Stage 2: Test paid boosts at simple weekly price points once landlords receive real inquiries.",
            "Stage 3: Add premium landlord tools such as analytics, renewal controls, and performance insights.",
            "Stage 4: Add verification, screening, and service-based monetization once trust and traffic improve.",
        ],
    },
    {
        "title": "Go-To-Market Recommendation",
        "bullets": [
            "Position the product narrowly as a free DFW rental marketplace for small landlords and renters.",
            "Use founder-led supply seeding and direct outreach before broader marketing.",
            "Prioritize local channels: Facebook groups, Reddit, community networks, and landlord referrals.",
            "Measure landlord success, not vanity traffic: inquiries, response speed, repeat listings, and conversations.",
            "Do not market this as a broad Craigslist replacement until one wedge is clearly working.",
        ],
    },
    {
        "title": "Top 5 Immediate Recommendations",
        "bullets": [
            "Narrow the product story to DFW rentals first.",
            "Strengthen trust, moderation, and quality signals before adding more feature breadth.",
            "Make guided search measurably improve outcomes, not just appearance.",
            "Track landlord success metrics as the primary health signal.",
            "Delay aggressive monetization until lead quality and repeat usage are visible.",
        ],
    },
    {
        "title": "Final Assessment",
        "bullets": [
            "This product is promising, not broken.",
            "It is strong enough for a controlled local validation launch.",
            "It is not yet mature enough for broad rollout or hard monetization.",
            "If the team proves supply, trust, and repeat landlord value in one city, the business can become meaningful.",
            "If those signals do not appear, more features alone are unlikely to change the outcome.",
        ],
    },
]


def xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def content_types_xml(slide_count: int) -> str:
    overrides = [
        ('/ppt/presentation.xml', 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'),
        ('/ppt/theme/theme1.xml', 'application/vnd.openxmlformats-officedocument.theme+xml'),
        ('/ppt/slideMasters/slideMaster1.xml', 'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml'),
        ('/ppt/slideLayouts/slideLayout1.xml', 'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml'),
        ('/docProps/core.xml', 'application/vnd.openxmlformats-package.core-properties+xml'),
        ('/docProps/app.xml', 'application/vnd.openxmlformats-officedocument.extended-properties+xml'),
    ]
    for i in range(1, slide_count + 1):
        overrides.append(
            (f'/ppt/slides/slide{i}.xml', 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml')
        )
    body = [
        xml_header(),
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    for part, content_type in overrides:
        body.append(f'<Override PartName="{part}" ContentType="{content_type}"/>')
    body.append('</Types>')
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
            '<Slides>%d</Slides>' % slide_count,
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
            '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>' % created,
            '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>' % created,
            '</cp:coreProperties>',
        ]
    )


def presentation_xml(slide_count: int) -> str:
    sld_ids = []
    base_id = 256
    for i in range(1, slide_count + 1):
        sld_ids.append(f'<p:sldId id="{base_id + i}" r:id="rId{i + 1}"/>')
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
            '<p:defaultTextStyle>',
            '<a:defPPr/><a:lvl1pPr marL="0" indent="0"><a:defRPr sz="2000"/></a:lvl1pPr>',
            '<a:lvl2pPr marL="457200" indent="0"><a:defRPr sz="1800"/></a:lvl2pPr>',
            '</p:defaultTextStyle>',
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
            '<p:cSld name="Office Theme">',
            '<p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>',
            '<p:spTree>',
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>',
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>',
            '</p:spTree>',
            '</p:cSld>',
            '<p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/>',
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>',
            '<p:txStyles>',
            '<p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="2800" b="1"/></a:lvl1pPr></p:titleStyle>',
            '<p:bodyStyle><a:lvl1pPr marL="0" indent="0"><a:defRPr sz="2000"/></a:lvl1pPr></p:bodyStyle>',
            '<p:otherStyle><a:defPPr/></p:otherStyle>',
            '</p:txStyles>',
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
            '</p:spTree></p:cSld>',
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>',
            '</p:sldLayout>',
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
            '<a:fmtScheme name="Listojo Format"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="lt1"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>',
            '</a:themeElements>',
            '<a:objectDefaults/><a:extraClrSchemeLst/>',
            '</a:theme>',
        ]
    )


def para_xml(text: str, level: int = 0, bullet: bool = False, size: int = 2200) -> str:
    escaped = escape(text)
    ppr = f'<a:pPr lvl="{level}">' + ('<a:buChar char="•"/>' if bullet else '<a:buNone/>') + '</a:pPr>'
    return f'<a:p>{ppr}<a:r><a:rPr lang="en-US" sz="{size}"/><a:t>{escaped}</a:t></a:r><a:endParaRPr lang="en-US" sz="{size}"/></a:p>'


def textbox_xml(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paragraphs: str) -> str:
    return "".join(
        [
            f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>',
            '<p:spPr><a:xfrm>',
            f'<a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>',
            '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>',
            '<a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>',
            '<p:txBody><a:bodyPr wrap="square" rtlCol="0" anchor="t"/><a:lstStyle/>',
            paragraphs,
            '</p:txBody></p:sp>',
        ]
    )


def accent_bar_xml(shape_id: int) -> str:
    return "".join(
        [
            f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="Accent Bar"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>',
            '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="12192000" cy="228600"/></a:xfrm>',
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>',
            '<a:solidFill><a:srgbClr val="2A7EF2"/></a:solidFill>',
            '<a:ln><a:noFill/></a:ln></p:spPr></p:sp>',
        ]
    )


def slide_xml(title: str, bullets: list[str], subtitle: str | None = None) -> str:
    shapes = [accent_bar_xml(2)]
    title_paras = para_xml(title, bullet=False, size=2600)
    shapes.append(textbox_xml(3, "Title", 609600, 411480, 10972800, 685800, title_paras))

    if subtitle:
        sub_paras = para_xml(subtitle, bullet=False, size=1600)
        shapes.append(textbox_xml(4, "Subtitle", 609600, 1127760, 10972800, 548640, sub_paras))
        body_y = 1737360
    else:
        body_y = 1270000

    bullet_paras = "".join(para_xml(item, bullet=True, size=1900) for item in bullets)
    body_height = 6858000 - body_y - 457200
    shapes.append(textbox_xml(5, "Body", 731520, body_y, 10668000, body_height, bullet_paras))

    return "".join(
        [
            xml_header(),
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ',
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">',
            '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="F8FAFC"/></a:solidFill></p:bgPr></p:bg>',
            '<p:spTree>',
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>',
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>',
            "".join(shapes),
            '</p:spTree></p:cSld>',
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>',
            '</p:sld>',
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


def build_pptx(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        slide_count = len(SLIDES)
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
        for idx, slide in enumerate(SLIDES, start=1):
            zf.writestr(
                f"ppt/slides/slide{idx}.xml",
                slide_xml(slide["title"], slide["bullets"], slide.get("subtitle")),
            )
            zf.writestr(f"ppt/slides/_rels/slide{idx}.xml.rels", slide_rels_xml())


if __name__ == "__main__":
    build_pptx(OUT_PATH)
    print(OUT_PATH)
