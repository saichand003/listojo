from __future__ import annotations

from pathlib import Path
import zipfile

from generate_ba_ppt import (
    add_title,
    app_xml,
    content_types_xml,
    core_xml,
    line_xml,
    para_xml,
    presentation_rels_xml,
    presentation_xml,
    rect_xml,
    root_rels_xml,
    slide_layout_rels_xml,
    slide_layout_xml,
    slide_master_rels_xml,
    slide_master_xml,
    slide_rels_xml,
    slide_xml_from_shapes,
    textbox_xml,
    theme_xml,
)


OUT_PATH = Path("/Users/saichandc/Documents/Test/Listojo_Business_Logic_Flow_Visual.pptx")


def build_business_logic_slide() -> str:
    shapes: list[str] = []

    add_title(
        shapes,
        "Listojo Business Logic Flow",
        "Simple view: how a visitor becomes a lead, gets help if needed, and creates business value",
    )

    # Summary banner
    shapes.append(rect_xml(20, "Banner", 800000, 1300000, 10500000, 550000, "E0F2FE", "93C5FD"))
    banner_text = (
        para_xml(
            "Listojo lets people search on their own first, then brings in an agent only when the user wants help or shows stronger intent.",
            size=1550,
            bold=True,
            color="0F172A",
        )
    )
    shapes.append(textbox_xml(21, "BannerText", 1050000, 1440000, 10000000, 300000, banner_text))

    # Main top-row flow boxes
    box_w = 1900000
    box_h = 1050000
    y = 2200000
    xs = [700000, 2950000, 5200000, 7600000]
    fills = ["DBEAFE", "DDF7F2", "FFF1D6", "FCE7F3"]
    titles = ["1. User Arrives", "2. Tell Us Needs", "3. See Curated Matches", "4. Need Agent Help?"]
    bodies = [
        "Visitor lands on Listojo to find a rental, home, or local option.",
        "Platform captures city, budget, bedrooms, timing, and preferences.",
        "User sees relevant results and can continue on a self-serve journey.",
        "This is the key business fork in the model.",
    ]
    title_colors = ["1E3A8A", "0F766E", "92400E", "9D174D"]

    sid = 30
    for i, x in enumerate(xs):
        radius = "diamond" if i == 3 else "roundRect"
        h = 1200000 if i == 3 else box_h
        w = 2100000 if i == 3 else box_w
        shapes.append(rect_xml(sid, f"Box{i+1}", x, y, w, h, fills[i], "CBD5E1", radius))
        shapes.append(
            textbox_xml(
                sid + 1,
                f"Box{i+1}Title",
                x + 140000,
                y + 120000,
                w - 280000,
                260000,
                para_xml(titles[i], size=1600, bold=True, color=title_colors[i]),
            )
        )
        shapes.append(
            textbox_xml(
                sid + 2,
                f"Box{i+1}Body",
                x + 140000,
                y + 410000,
                w - 280000,
                520000,
                para_xml(bodies[i], size=1350, color="334155"),
            )
        )
        sid += 3

    # Top row connectors
    shapes.append(line_xml(50, 2600000, 2730000, 2950000, 2730000, "94A3B8"))
    shapes.append(line_xml(51, 4850000, 2730000, 5200000, 2730000, "94A3B8"))
    shapes.append(line_xml(52, 7100000, 2730000, 7600000, 2730000, "94A3B8"))

    # Branch boxes
    left_x = 6100000
    right_x = 9200000
    branch_y = 4150000
    branch_w = 2300000
    branch_h = 1050000

    shapes.append(rect_xml(60, "SelfServe", left_x, branch_y, branch_w, branch_h, "E6F6E9", "A7F3D0"))
    shapes.append(
        textbox_xml(
            61,
            "SelfServeTitle",
            left_x + 150000,
            branch_y + 130000,
            1900000,
            240000,
            para_xml("5A. Self-Serve Path", size=1600, bold=True, color="166534"),
        )
    )
    shapes.append(
        textbox_xml(
            62,
            "SelfServeBody",
            left_x + 150000,
            branch_y + 420000,
            1900000,
            420000,
            para_xml("User keeps browsing independently. If intent rises later, the platform can still offer agent help.", size=1350, color="334155"),
        )
    )

    shapes.append(rect_xml(63, "AgentPath", right_x, branch_y, branch_w, branch_h, "FCE8E8", "FCA5A5"))
    shapes.append(
        textbox_xml(
            64,
            "AgentPathTitle",
            right_x + 150000,
            branch_y + 130000,
            1900000,
            240000,
            para_xml("5B. Agent Path", size=1600, bold=True, color="B91C1C"),
        )
    )
    shapes.append(
        textbox_xml(
            65,
            "AgentPathBody",
            right_x + 150000,
            branch_y + 420000,
            1900000,
            420000,
            para_xml("Lead is assigned to an agent, who reviews preferences, curates options, and follows up.", size=1350, color="334155"),
        )
    )

    # Branch connectors from decision box
    shapes.append(line_xml(66, 8650000, 3400000, 7250000, 4150000, "94A3B8"))
    shapes.append(line_xml(67, 9250000, 3400000, 10350000, 4150000, "94A3B8"))
    shapes.append(textbox_xml(68, "NoLabel", 6750000, 3520000, 450000, 180000, para_xml("No", size=1200, bold=True, color="475569")))
    shapes.append(textbox_xml(69, "YesLabel", 9700000, 3520000, 450000, 180000, para_xml("Yes", size=1200, bold=True, color="475569")))

    # Outcome / business value bars
    shapes.append(rect_xml(70, "Outcome", 3600000, 5600000, 3000000, 550000, "FEF3C7", "FCD34D"))
    shapes.append(
        textbox_xml(
            71,
            "OutcomeText",
            3860000,
            5760000,
            2500000,
            240000,
            para_xml("6. Better User Outcome", size=1650, bold=True, color="92400E")
            + para_xml("Faster search, more relevant matches, and optional expert help.", size=1300, color="334155"),
        )
    )

    shapes.append(rect_xml(72, "BusinessValue", 7000000, 5600000, 4200000, 550000, "EDE9FE", "C4B5FD"))
    shapes.append(
        textbox_xml(
            73,
            "BusinessValueText",
            7260000,
            5760000,
            3600000,
            260000,
            para_xml("7. Business Value", size=1650, bold=True, color="6D28D9")
            + para_xml("Lead intelligence, agent conversion, referral revenue, and funnel visibility.", size=1300, color="334155"),
        )
    )

    # Connectors to outcomes
    shapes.append(line_xml(74, 7250000, 5200000, 5950000, 5600000, "94A3B8"))
    shapes.append(line_xml(75, 10350000, 5200000, 9100000, 5600000, "94A3B8"))

    # Bottom callouts
    shapes.append(rect_xml(80, "CalloutA", 700000, 5250000, 2500000, 1050000, "EFF6FF", "BFDBFE"))
    callout_a = (
        para_xml("Why this works", size=1550, bold=True, color="1E3A8A")
        + para_xml("People get value before talking to anyone, so the experience feels useful instead of pushy.", size=1280, color="334155")
    )
    shapes.append(textbox_xml(81, "CalloutAText", 900000, 5420000, 2100000, 620000, callout_a))

    shapes.append(rect_xml(82, "CalloutB", 700000, 4100000, 2500000, 950000, "F0FDF4", "BBF7D0"))
    callout_b = (
        para_xml("Revenue logic", size=1550, bold=True, color="166534")
        + para_xml("Money comes later, when qualified demand becomes an attributable agent-assisted outcome.", size=1280, color="334155")
    )
    shapes.append(textbox_xml(83, "CalloutBText", 900000, 4260000, 2100000, 560000, callout_b))

    return slide_xml_from_shapes(shapes)


SLIDES = [build_business_logic_slide]


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
