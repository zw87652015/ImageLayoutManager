# Implementation Plan: Infinite Workspace & "Magic Paper" Canvases

## 1. Vision
Transform ImageLayoutManager from a fixed-page grid editor into a **tactile design environment**. The user works in an infinite workspace where independent "Canvases" (grids) behave like pieces of paper that can be dragged, snapped together magnetically, and automatically resized.

## 2. Core Concepts

### 2.1 The "Magic Paper" Canvas
Each Canvas is a standalone grid area.
- **Content-Driven Size:** The width and height of the Canvas are determined by its internal grid (rows/columns).
- **Dynamic Growth:** Adding a row physically expands the Canvas boundary in the workspace.
- **Grid Independence:** Each Canvas maintains its own gap settings, margins, and label schemes.

### 2.2 The Infinite Workspace
The workspace is a pannable, zoomable 2D scene that hosts multiple Canvases.
- **Coordinate System:** Canvases have absolute `(x, y)` positions in the workspace (measured in mm).
- **Cluster Detection:** The system detects when canvases are "snapped" (clicked) together based on shared edges.

### 2.3 Magnetic Snapping (The "Glue")
- **Edge Attraction:** When an edge of "Canvas A" comes within a threshold of "Canvas B," it "clicks" into place.
- **Snap Indicators:** Visual lines appear to show alignment.
- **Group Movement:** Snapped Canvases move as a single unit.

---

## 3. Data Model Changes (`src/model/data_model.py`)

The `Project` becomes a container for multiple `Canvas` instances.

```python
@dataclass
class Canvas:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Canvas 1"
    x: float = 0.0  # Workspace X (mm)
    y: float = 0.0  # Workspace Y (mm)
    rows: List[RowTemplate] = field(default_factory=list)
    cells: List[Cell] = field(default_factory=list)
```

---

## 4. Advanced Export Logic

The exporter will dynamically determine the output based on the workspace arrangement:

### 4.1 Discrete Papers (Batch Mode)
- Any Canvas (or cluster) that is not touching another is exported as a **separate file**.
- This allows a user to maintain 10 different figures in one project file and export them all at once.

### 4.2 Snapped Groups (Composite Mode)
- **Rectangular Groups:** If a group of snapped canvases forms a perfect rectangle, that rectangle is the export area.
- **Staggered Groups:** If the arrangement is non-rectangular (e.g., L-shaped), the export area is the **smallest bounding rectangle** that covers all canvases.
- **Transparency/Padding:** Empty space in the bounding box is filled with either **Pure White** or **Transparency** (user selection).

---

## 5. Implementation Roadmap

### Phase 1: Workspace Foundation
- Refactor `Project` and `Canvas` data structures.
- Implement the "Baking" migration for old single-grid files.
- **UI:** Implement Workspace Panning and Zooming.

### Phase 2: Interaction & Snapping
- Implement Canvas Drag-and-Drop.
- Build the **Magnetic Snapping Engine**.
- Add visual alignment guides.

### Phase 3: Export Engine Upgrade
- Implement "Cluster Detection" logic.
- Update TIFF/PNG/PDF exporters to handle multiple output files/areas.
- Add "Export Fill Color" to the Export Dialog.
