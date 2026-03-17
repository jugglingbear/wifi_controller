# Architecture

This directory contains PlantUML diagrams describing the `wifi_controller` architecture.

## Diagrams

| File | Description |
|------|-------------|
| [class_diagram.puml](class_diagram.puml) | Provider ABCs, WiFiController, and all built-in implementations |
| [sequence_diagram.puml](sequence_diagram.puml) | Provider resolution and operation flow |
| [component_diagram.puml](component_diagram.puml) | Package structure and platform boundaries |

## Rendering

Render with any PlantUML tool:

```bash
# CLI (requires Java + plantuml.jar)
plantuml docs/*.puml

# Docker
docker run --rm -v $(pwd)/docs:/data plantuml/plantuml *.puml

# VS Code extension: "PlantUML" by jebbs (Alt+D to preview)
```

Or paste into [plantuml.com/plantuml](https://www.plantuml.com/plantuml/uml/).
