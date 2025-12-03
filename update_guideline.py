import yaml

def generate_markdown(yaml_file, output_file):
    with open(yaml_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    lines = []
    
    # --- Static Header ---
    lines.extend([
        "# PartDB Guideline",
        "",
        "# **Living Documents - Not Released!!!**",
        "",
        "# **Component Library Architecture**",
        "",
        "## **1\. Philosophy and Goals:**",
        "",
        "- **Automated BOM Analysis:** Cost estimation, availability checks, and mass calculation.",
        "- **Compliance Tracking:** Instant generation of RoHS/REACH/UL reports.",
        "- **Design Validation:** Automated checks for power ratings and thermal constraints.",
        "- **Reliability Prediction:** MTBF (Mean Time Between Failures) calculations based on stored FIT rates.",
        "",
        "## **2\. PartDB Native Fields (Standard Tabs)**",
        "",
        "#### **A. Tab: Common**",
        "",
        "- **Name:** **MUST be the MPN (Manufacturer Part Number).**",
        "- **Description:** Strict technical description.",
        "    - _Format passives:_ `[Category] [Values] [Tolerance] [Package]` (e.g., `RES 10k 1/10W 1% 0603`).",
        "    - _Format actives:_ `[Category] [Features] [Package]` (e.g., `OpAmp Dual Channel Rail to Rail`).",
        "- **Category:** Select from the tree structure (defined in Section 4).",
        "- **Tags:** Not mandatory",
        "- **Minimum Stock:** N/A",
        "- **Footprint:** The physical land pattern name.",
        "    - _Format:_ `[Manufacturer]_[Drawing Number]_[Footprint Name]` (e.g., `TI_DGK0008A_VSSOP8`).",
        "",
        "#### **B. Tab: Manufacturer**",
        "",
        "- **Manufacturer:** The actual silicon/part producer (e.g., `Texas Instruments`).",
        "- **Manufacturer Part Number:** Manufacturer Part Number.",
        "- **Link to Product Page:** URL to the specific component page on the MFG website.",
        "- **Manufacturing Status:**",
        "    - _PartDB Mapping (_**_Must not be NRND or Obsolete when creating part)_**_:_",
        "    - _Managed via API/Automatic Updates_",
        "        - `Active` = Preferred for new designs.",
        "        - `NRND` = Not Recommended for New Designs.",
        "        - `Obsolete` = Do not use.",
        "        - `Preliminary` = Risk assessment required.",
        "",
        "#### **C. Tab: Advanced**",
        "",
        "- **Mass:** Component weight in **grams (g)**.",
        "- **Internal Part Number:** N/A",
        "- **Measuring Unit:** N/A",
        "",
        "#### **D. Tab: Purchase Information**",
        "",
        "- **Supplier:** Primary Distributor (e.g., DigiKey, Mouser).",
        "- **Supplier PN:** The distributor's SKU (used for API pricing fetch).",
        "- **Link to Offer:** Direct URL to the distributor's product page.",
        "- **Price:** _Managed via API/Automatic Updates_ (Do not manually populate).",
        ""
    ])

    # --- Section 3: Global Parameters ---
    lines.extend([
        "### **3\. PartDB Parameters Tab (Custom Globals)**",
        "",
        "#### **A. Reliability & Ratings (Mandatory)**",
        ""
    ])
    
    # Heuristic grouping based on names, or just list them all?
    # The user had them grouped. I'll try to group them similarly if possible, 
    # or just list them. The user's YAML doesn't have grouping metadata.
    # I will list them all for now, or try to match the user's previous manual grouping if I can.
    # User's groups: Reliability & Ratings, Compliance & Environment.
    
    globals = data.get('global_parameters', [])
    
    # Simple mapping for now:
    for p in globals:
        name = p['name']
        unit = p.get('unit')
        symbol = p.get('symbol')
        
        desc = f"- `{name}`**:**"
        if unit:
            desc += f" ({unit})"
        if symbol:
            desc += f" [{symbol}]"
        lines.append(desc)
        
    lines.append("")

    # --- Section 4: Category Tree ---
    lines.extend([
        "### **4\. Category Tree & Specific Parameters**",
        "",
        "Structure PartDB categories exactly as follows. Parameters listed are _in addition_ to the Globals above. Subcategories shall be extended if needed.",
        ""
    ])

    categories = data.get('categories', [])
    
    for i, cat in enumerate(categories, 1):
        # Level 1
        lines.append(f"#### **{i}.0 {cat['name']}**")
        lines.append("")
        
        params = cat.get('parameters', [])
        if params:
            p_list = [f"`{p['name']}`" for p in params]
            lines.append(f"- **Shared Parameters:** {', '.join(p_list)}")
        
        children = cat.get('children', [])
        for j, child in enumerate(children, 1):
            # Level 2
            c_name = child['name']
            c_params = child.get('parameters', [])
            
            line = f"    - **{i}.{j} {c_name}**"
            if c_params:
                cp_list = [f"`{p['name']}`" for p in c_params]
                line += f": -> Add {', '.join(cp_list)}"
            lines.append(line)
            
            # Level 3 (if any)
            grand_children = child.get('children', [])
            for k, grand in enumerate(grand_children, 1):
                 gc_name = grand['name']
                 gc_params = grand.get('parameters', [])
                 line = f"        - **{i}.{j}.{k} {gc_name}**"
                 if gc_params:
                     gcp_list = [f"`{p['name']}`" for p in gc_params]
                     line += f": {', '.join(gcp_list)}"
                 lines.append(line)
        
        lines.append("")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    print(f"Successfully updated {output_file}")

if __name__ == "__main__":
    generate_markdown("categories.yaml", "PartDB Guideline.md")
