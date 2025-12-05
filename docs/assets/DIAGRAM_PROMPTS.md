# Nano Banano Pro Image Generation Prompts for PSDL

Use these prompts with Nano Banano Pro (https://nanobananopro.com) to generate professional diagrams for the PSDL project.

## API Key Setup
Your Google API key is stored in `.env`:
```
GOOGLE_API_KEY=AIzaSyB6hf7gSnKmslrNxZoclSPflaXUS6jPELc
```

---

## 1. Fragmentation Diagram (fragmentation-diagram.png)

**Prompt:**
```
Create a professional technical diagram showing clinical logic fragmentation in healthcare.

Left side shows chaos: scattered icons for Python scripts, SQL queries, EHR vendor systems, Jupyter notebooks, all disconnected with red X marks between them. Labels: "Non-portable", "No versioning", "No audit trail", "Vendor lock-in".

Right side shows PSDL solution: a single central YAML file icon labeled "PSDL Scenario" with clean arrows connecting to unified outputs.

Style: Modern tech documentation, dark navy background (#1a1a2e), cyan/teal accents (#00d9ff), clean sans-serif fonts, corporate healthcare tech aesthetic. 1200x600 pixels, 16:9 aspect ratio.
```

---

## 2. Before/After PSDL Comparison (before-after-psdl.png)

**Prompt:**
```
Create a professional split-screen comparison diagram for software documentation.

LEFT PANEL - "Before PSDL":
- Red/orange tint
- Messy pile of file icons (.py, .sql, .json, .ipynb)
- Tangled lines connecting them
- Warning symbols
- Text bullets: "300+ lines Python", "4+ SQL queries", "Multiple config files", "Manual audit"

RIGHT PANEL - "After PSDL":
- Green/teal tint
- Single clean YAML file icon
- Organized flowchart: Signals → Trends → Logic → Triggers
- Checkmarks
- Text bullets: "50 lines YAML", "Auto-generated SQL", "Single source of truth", "Built-in audit"

Style: Modern SaaS product comparison, gradient backgrounds, clean icons, professional healthcare tech aesthetic. 1400x700 pixels.
```

---

## 3. Runtime Architecture Diagram (runtime-architecture.png)

**Prompt:**
```
Create a technical architecture diagram showing PSDL runtime execution.

TOP LAYER: Data Sources
- FHIR icon, OMOP database icon, Streaming data icon

MIDDLE LAYER (highlighted in gold/yellow): PSDL Semantic Layer
- Parser → Mapper → Evaluator → Executor pipeline
- Central PSDL logo/badge

BOTTOM LAYER: Runtime Targets
- SQL Runtime, FHIR Runtime, Python Runtime, Stream Runtime (Kafka/Flink)

Show data flow with arrows. Include small icons for each component.

Style: Enterprise software architecture diagram, dark theme (#0d1117), accent colors cyan (#58a6ff) and gold (#f0b429), professional look suitable for technical documentation. 1200x800 pixels.
```

---

## 4. Roadmap Timeline (roadmap-timeline.png)

**Prompt:**
```
Create a horizontal roadmap timeline diagram for an open source project.

Four phases connected by a flowing line:

Phase 1 - SEMANTIC FOUNDATION (highlighted as current, green checkmark)
- Type system ✓
- Parser ✓
- Evaluator ✓

Phase 2 - ENHANCED RUNTIME
- OMOP SQL backend
- FHIR backend
- Conformance tests

Phase 3 - COMMUNITY BUILDING
- Technical blogs
- Conference talks
- Discord/GitHub

Phase 4 - ADOPTION
- Hospital pilots
- HL7/OHDSI engagement
- Third-party implementations

Style: Modern product roadmap, horizontal timeline with milestones, gradient from current (green) to future (blue), clean minimalist design, suitable for README. 1400x400 pixels, wide format.
```

---

## 5. Ecosystem Vision Diagram (psdl-ecosystem.png)

**Prompt:**
```
Create a circular ecosystem diagram showing PSDL at the center with stakeholders around it.

CENTER: PSDL logo with "Open Standard" text

SURROUNDING STAKEHOLDERS (in a circle):
- Hospitals & Health Systems (building icon)
- Researchers (graduation cap icon)
- EHR Vendors (server icon)
- AI/ML Developers (brain/chip icon)
- Regulators (shield/checkmark icon)
- Standards Bodies (globe icon)

Bidirectional arrows connecting center to each stakeholder.

Style: Modern ecosystem/platform diagram, dark gradient background, glowing connections, healthcare tech aesthetic, professional and aspirational. 1000x1000 pixels, square format.
```

---

## 6. Scenario Semantics Gap Illustration (scenario-semantics-gap.png)

**Prompt:**
```
Create a diagram illustrating the "scenario semantics gap" in healthcare AI.

LEFT SIDE:
- ML Model icon with "90% Accuracy" badge
- Glowing, optimistic

CENTER (the gap):
- Broken bridge or chasm
- Question marks floating
- "When?", "Which patients?", "What signals?", "What actions?"

RIGHT SIDE:
- Clinical Workflow icon
- Hospital/bedside illustration
- Dimmed, unreachable

Show PSDL as the bridge that fills this gap (optional: golden bridge labeled "PSDL")

Style: Conceptual illustration, professional tech documentation style, shows problem clearly, blue/gray palette with gold accent for solution. 1200x600 pixels.
```

---

## Tips for Best Results

1. **Aspect Ratio**: Use 16:9 for wide diagrams, 1:1 for ecosystem diagrams
2. **Colors**: Stick to the PSDL palette:
   - Primary: Navy (#1a1a2e), Teal (#00d9ff)
   - Accents: Gold (#f0b429), Green (#22c55e)
3. **Style**: Request "technical documentation", "enterprise software", or "healthcare tech" aesthetics
4. **Text**: Keep text minimal in images, add labels in markdown instead
5. **Resolution**: Request at least 1200px width for README display

---

## Usage

After generating images with Nano Banano Pro:

1. Save images to `/docs/assets/`
2. Update the whitepaper to use actual images instead of ASCII diagrams
3. Consider creating both light and dark mode versions

---

*Generated for PSDL - Patient Scenario Definition Language*
